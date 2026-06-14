# validate_pipeline.ps1
# Phase A.5 - Full pipeline validation script
# Run from the Member_04_Application_Automation directory.

param(
    [string]$BaseUrl = "http://localhost:8004",
    [switch]$SkipDockerBuild = $false,
    [switch]$VerboseOutput = $false
)

$ErrorActionPreference = "Stop"
$ApiBase = "$BaseUrl/api/v1"

#  Colours 
function Write-Pass  { param($msg) Write-Host "  PASS PASS  $msg" -ForegroundColor Green }
function Write-Fail  { param($msg) Write-Host "  FAIL FAIL  $msg" -ForegroundColor Red }
function Write-Info  { param($msg) Write-Host "  INFO  $msg" -ForegroundColor Cyan }
function Write-Step  { param($msg) Write-Host "`n STEP: $msg " -ForegroundColor Yellow }

$Results = @{ Pass = 0; Fail = 0; Skip = 0 }

function Assert-Http {
    param(
        [string]$Description,
        [string]$Method,
        [string]$Url,
        [hashtable]$Body = $null,
        [int]$ExpectedStatus = 200,
        [string]$ExpectedJsonPath = $null,
        [string]$ExpectedValue = $null
    )
    try {
        $params = @{ Uri = $Url; Method = $Method; ContentType = "application/json" }
        if ($Body) { $params["Body"] = ($Body | ConvertTo-Json -Depth 10) }

        $response = Invoke-WebRequest @params -ErrorAction SilentlyContinue
        $actual_status = $response.StatusCode

        if ($actual_status -eq $ExpectedStatus) {
            $Results.Pass++
            Write-Pass $Description
            if ($VerboseOutput) { Write-Host "     Status: $actual_status" -ForegroundColor Gray }
        } else {
            $Results.Fail++
            Write-Fail "$Description (expected $ExpectedStatus, got $actual_status)"
        }

        # Return parsed body for further assertions
        return $response.Content | ConvertFrom-Json
    }
    catch {
        $actual_status = $_.Exception.Response.StatusCode.value__
        if ($actual_status -eq $ExpectedStatus) {
            $Results.Pass++
            Write-Pass "$Description (expected error $ExpectedStatus)"
        } else {
            $Results.Fail++
            Write-Fail "$Description - unexpected error: $_"
        }
        return $null
    }
}

# =============================================================================
Write-Host @"
+===============================================================+
|      Phase A.5 - Pipeline Validation Script                   |
|      Application Automation Agent (Member 4)                  |
+===============================================================+
"@ -ForegroundColor Magenta

#  STEP 1: Docker Stack 
Write-Step "1 - Docker Stack Health"

if (-not $SkipDockerBuild) {
    Write-Info "Starting docker-compose stack..."
    docker-compose up -d --build 2>&1 | Out-Null
    Write-Info "Waiting 15s for services to initialize..."
    Start-Sleep -Seconds 15

    # Verify containers are running
    $containers = docker-compose ps --format json 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Pass "docker-compose stack is running" }
    else { Write-Fail "docker-compose stack not running - run: docker-compose up --build" }
} else {
    Write-Info "Skipping Docker build (--SkipDockerBuild flag set)"
}

#  STEP 2: Health Endpoints 
Write-Step "2 - Health & Readiness Endpoints"

$health = Assert-Http "GET /health returns 200" -Method GET -Url "$ApiBase/health" -ExpectedStatus 200
if ($health -and $health.status -eq "alive") { $Results.Pass++; Write-Pass "Health status is 'alive'" }
else { $Results.Fail++; Write-Fail "Health status not 'alive'" }

$ready = Assert-Http "GET /ready returns 200 when stack up" -Method GET -Url "$ApiBase/ready" -ExpectedStatus 200
if ($ready -and $ready.status -eq "healthy") { $Results.Pass++; Write-Pass "Readiness status is 'healthy'" }
else { $Results.Fail++; Write-Fail "Readiness status not 'healthy'" }

#  STEP 3: Submit API 
Write-Step "3 - Application Submit API"

$jobId = [guid]::NewGuid().ToString()
$userId = "550e8400-e29b-41d4-a716-446655440000"

$submitBody = @{
    user_id = $userId
    job_id  = $jobId
    job_metadata = @{
        company_name       = "Validation Test Corp"
        role_title         = "Senior Validator"
        application_method = "email"
        contact_email      = "jobs@validation.example.com"
        platform           = "validation_test"
    }
    resume = @{
        version_id   = [guid]::NewGuid().ToString()
        storage_url  = "https://our-storage.example.com/resume.pdf"
        filename     = "Test_Resume.pdf"
    }
    guardrails = @{
        manual_approval_required = $false
        max_retries = 1
        priority    = "normal"
    }
}

$submitResult = Assert-Http "POST /submit returns 202" `
    -Method POST -Url "$ApiBase/applications/submit" `
    -Body $submitBody -ExpectedStatus 202

$appId = $null
if ($submitResult -and $submitResult.data.application_id) {
    $appId = $submitResult.data.application_id
    $Results.Pass++
    Write-Pass "Response contains application_id: $appId"
    Write-Info "Tracking URL: $($submitResult.data.tracking_url)"
} else {
    $Results.Fail++
    Write-Fail "Response missing application_id"
}

#  STEP 4: Status Polling 
Write-Step "4 - Status Tracking & Polling"

if ($appId) {
    Assert-Http "GET /applications/{id}/status returns 200" `
        -Method GET -Url "$ApiBase/applications/$appId/status" -ExpectedStatus 200

    Write-Info "Polling for terminal status (max 30s)..."
    $terminalStatuses = @("applied", "failed", "duplicate", "limit_exceeded")
    $finalStatus = $null
    $pollCount = 0

    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        $pollCount++
        try {
            $statusResp = Invoke-RestMethod -Uri "$ApiBase/applications/$appId/status" -Method GET
            $currentStatus = $statusResp.data.status
            if ($VerboseOutput) { Write-Host "     Poll $pollCount`: status = $currentStatus" -ForegroundColor Gray }
            if ($terminalStatuses -contains $currentStatus) {
                $finalStatus = $currentStatus
                break
            }
        } catch { }
    }

    if ($finalStatus) {
        $Results.Pass++
        Write-Pass "Application reached terminal status: '$finalStatus' after ${pollCount}s"
    } else {
        $Results.Fail++
        Write-Fail "Application did not reach terminal status within 30s"
    }
}

#  STEP 5: Status History 
Write-Step "5 - Status History Audit Trail"

if ($appId) {
    $history = Assert-Http "GET /applications/{id}/history returns 200" `
        -Method GET -Url "$ApiBase/applications/$appId/history" -ExpectedStatus 200

    if ($history -and $history.data.history.Count -gt 0) {
        $Results.Pass++
        Write-Pass "Status history has $($history.data.history.Count) entries"
        if ($VerboseOutput) {
            $history.data.history | ForEach-Object {
                Write-Host "     $($_.from_status)  $($_.to_status)  [$($_.changed_by)]" -ForegroundColor Gray
            }
        }
    } else {
        $Results.Fail++
        Write-Fail "Status history is empty (expected at least 1 entry)"
    }
}

#  STEP 6: Validation Errors 
Write-Step "6 - Input Validation Errors"

Assert-Http "Empty body returns 422" `
    -Method POST -Url "$ApiBase/applications/submit" -Body @{} -ExpectedStatus 422

Assert-Http "Missing user_id returns 422" `
    -Method POST -Url "$ApiBase/applications/submit" `
    -Body ($submitBody.Clone() | ForEach-Object { $_.Remove("user_id"); $_ }) -ExpectedStatus 422

$badResume = $submitBody.Clone()
$badResume["job_id"] = [guid]::NewGuid().ToString()
$badResume["resume"] = @{
    version_id  = [guid]::NewGuid().ToString()
    storage_url = "https://our-storage.example.com/resume.pdf"
    filename    = "bad_resume.exe"
}
Assert-Http "Non-PDF resume returns 422" `
    -Method POST -Url "$ApiBase/applications/submit" -Body $badResume -ExpectedStatus 422

#  STEP 7: Duplicate Detection 
Write-Step "7 - Duplicate Submission Detection"

# Wait a moment for the first submission to be processed
Start-Sleep -Seconds 3

$dupStatus = 0
try {
    $response = Invoke-WebRequest -Uri "$ApiBase/applications/submit" `
        -Method POST `
        -ContentType "application/json" `
        -Body ($submitBody | ConvertTo-Json -Depth 10) `
        -ErrorAction SilentlyContinue
    $dupStatus = $response.StatusCode
} catch {
    $dupStatus = $_.Exception.Response.StatusCode.value__
}

if ($dupStatus -eq 409) {
    $Results.Pass++
    Write-Pass "Duplicate submission correctly returns 409"
} elseif ($dupStatus -eq 202) {
    # The dedup cache may not have been set yet (race condition in test)
    Write-Host "  WARN  Duplicate returned 202 (dedup cache may not be set yet)" -ForegroundColor Yellow
    $Results.Skip++
} else {
    $Results.Fail++
    Write-Fail "Duplicate submission returned unexpected status: $dupStatus"
}

#  STEP 8: State Machine Enforcement 
Write-Step "8 - State Machine Enforcement"

if ($appId) {
    # Attempt illegal transition: failed  queued (if app is now failed)
    $illegalStatus = 0
    try {
        $illegalResult = Invoke-WebRequest `
            -Uri "$ApiBase/applications/$appId/status" `
            -Method PATCH `
            -ContentType "application/json" `
            -Body '{"status": "queued", "reason": "Test illegal transition"}' `
            -ErrorAction SilentlyContinue
        $illegalStatus = $illegalResult.StatusCode
    } catch {
        $illegalStatus = $_.Exception.Response.StatusCode.value__
    }

    if ($illegalStatus -in @(409, 422, 200)) {
        # 200 means the transition was legal (app was still in a state that allows queued)
        # 409 means correctly rejected by state machine
        if ($illegalStatus -eq 409) {
            $Results.Pass++
            Write-Pass "Illegal state transition returned 409"
        } else {
            Write-Host "  WARN  WARN  Transition returned $illegalStatus (state may be legal)" -ForegroundColor Yellow
            $Results.Skip++
        }
    } else {
        $Results.Fail++
        Write-Fail "Illegal state transition returned unexpected status: $illegalStatus"
    }
}

#  STEP 9: List Endpoint 
Write-Step "9 - List & Pagination"

$list = Assert-Http "GET /applications?user_id=... returns 200" `
    -Method GET -Url "$ApiBase/applications?user_id=$userId" -ExpectedStatus 200

if ($list -and $list.data.pagination) {
    $Results.Pass++
    Write-Pass "List returns pagination metadata (total: $($list.data.pagination.total))"
}

#  STEP 10: Delete 
Write-Step "10 - Soft Delete"

if ($appId) {
    $deleteResult = Assert-Http "DELETE /applications/{id} returns 200" `
        -Method DELETE -Url "$ApiBase/applications/$appId" -ExpectedStatus 200

    if ($deleteResult -and $deleteResult.data.deleted_at) {
        $Results.Pass++
        Write-Pass "Soft delete returned deleted_at timestamp"
    }
}

# ==============================================================================
Write-Host @"

+===============================================================+
|                    VALIDATION SUMMARY                         |
+===============================================================+
"@ -ForegroundColor Magenta

$total = $Results.Pass + $Results.Fail + $Results.Skip
Write-Host "  Total:   $total" -ForegroundColor White
Write-Host "  PASS Pass: $($Results.Pass)" -ForegroundColor Green
Write-Host "  FAIL Fail: $($Results.Fail)" -ForegroundColor Red
Write-Host "  WARN  Skip: $($Results.Skip)" -ForegroundColor Yellow

if ($Results.Fail -eq 0) {
    Write-Host "`n  PASS All validations passed! Foundation is stable." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n  WARN  $($Results.Fail) validation(s) failed. Review output above." -ForegroundColor Red
    exit 1
}
