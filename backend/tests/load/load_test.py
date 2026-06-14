"""
Load Test Script — Phase A.5 Performance Baseline

PURPOSE: Establish baseline metrics for the async pipeline.
         DO NOT optimize yet — only measure and record.

PREREQUISITES: The full Docker stack must be running.
    docker-compose up --build

USAGE:
    # Install httpx if not already installed
    pip install httpx

    # Run baseline (50 submissions)
    python tests/load/load_test.py --count 50

    # Run concurrency test (20 concurrent)
    python tests/load/load_test.py --count 100 --concurrency 20

    # Run and save results
    python tests/load/load_test.py --count 50 --output results.json

METRICS COLLECTED:
    - Submit endpoint latency (p50, p95, p99)
    - Status poll latency
    - Queue processing delay (time from submit to "applied")
    - Throughput (requests/second)
    - Error rate
"""
import asyncio
import json
import statistics
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, UTC
from typing import Optional
import argparse

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx")
    raise

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8004/api/v1"
DEFAULT_COUNT = 50
DEFAULT_CONCURRENCY = 10
MAX_POLL_SECONDS = 30
POLL_INTERVAL_SECONDS = 1.0
TEST_USER_ID = "550e8400-e29b-41d4-a716-446655440000"

# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class SubmitResult:
    job_id: str
    application_id: Optional[str] = None
    submit_latency_ms: float = 0.0
    submit_success: bool = False
    submit_error: Optional[str] = None
    final_status: Optional[str] = None
    processing_time_ms: Optional[float] = None
    poll_attempts: int = 0


@dataclass
class LoadTestReport:
    total_submissions: int = 0
    successful_submits: int = 0
    failed_submits: int = 0
    submit_latencies_ms: list[float] = field(default_factory=list)
    processing_times_ms: list[float] = field(default_factory=list)
    final_statuses: dict[str, int] = field(default_factory=dict)
    started_at: str = ""
    completed_at: str = ""
    total_elapsed_seconds: float = 0.0

    def add_result(self, result: SubmitResult):
        self.total_submissions += 1
        if result.submit_success:
            self.successful_submits += 1
            self.submit_latencies_ms.append(result.submit_latency_ms)
        else:
            self.failed_submits += 1

        if result.final_status:
            self.final_statuses[result.final_status] = (
                self.final_statuses.get(result.final_status, 0) + 1
            )
        if result.processing_time_ms is not None:
            self.processing_times_ms.append(result.processing_time_ms)

    def percentile(self, data: list[float], p: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * p / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def print_summary(self):
        print("\n" + "=" * 60)
        print("  LOAD TEST RESULTS — Phase A.5 Performance Baseline")
        print("=" * 60)

        print(f"\n  Total submissions:   {self.total_submissions}")
        print(f"  Successful submits:  {self.successful_submits}")
        print(f"  Failed submits:      {self.failed_submits}")
        print(f"  Error rate:          {self.failed_submits / max(self.total_submissions, 1) * 100:.1f}%")
        print(f"  Total elapsed:       {self.total_elapsed_seconds:.2f}s")
        print(f"  Throughput:          {self.total_submissions / max(self.total_elapsed_seconds, 0.001):.1f} req/s")

        if self.submit_latencies_ms:
            print(f"\n  Submit Latency:")
            print(f"    p50:  {self.percentile(self.submit_latencies_ms, 50):.1f}ms")
            print(f"    p95:  {self.percentile(self.submit_latencies_ms, 95):.1f}ms")
            print(f"    p99:  {self.percentile(self.submit_latencies_ms, 99):.1f}ms")
            print(f"    max:  {max(self.submit_latencies_ms):.1f}ms")
            print(f"    mean: {statistics.mean(self.submit_latencies_ms):.1f}ms")

        if self.processing_times_ms:
            print(f"\n  Processing Time (submit → applied):")
            print(f"    p50:  {self.percentile(self.processing_times_ms, 50):.0f}ms")
            print(f"    p95:  {self.percentile(self.processing_times_ms, 95):.0f}ms")
            print(f"    mean: {statistics.mean(self.processing_times_ms):.0f}ms")

        if self.final_statuses:
            print(f"\n  Final Statuses:")
            for status, count in sorted(self.final_statuses.items()):
                pct = count / max(self.total_submissions, 1) * 100
                print(f"    {status:<25} {count:>4}  ({pct:.1f}%)")

        print("\n" + "=" * 60)


# ── Request builders ───────────────────────────────────────────────────────────

def make_submission_payload(job_id: str) -> dict:
    return {
        "user_id": TEST_USER_ID,
        "job_id": job_id,
        "job_metadata": {
            "company_name": f"LoadTest Corp {job_id[:8]}",
            "role_title": "Engineer",
            "application_method": "email",
            "contact_email": "jobs@loadtest.example.com",
            "platform": "load_test",
        },
        "resume": {
            "version_id": str(uuid.uuid4()),
            "storage_url": "https://our-storage.example.com/test_resume.pdf",
            "filename": "LoadTest_Resume.pdf",
        },
        "guardrails": {
            "manual_approval_required": False,
            "max_retries": 1,
            "priority": "normal",
        },
    }


# ── Core test functions ────────────────────────────────────────────────────────

async def submit_one(client: httpx.AsyncClient, job_id: str) -> SubmitResult:
    """Submit one application and return the result."""
    result = SubmitResult(job_id=job_id)
    t_start = time.monotonic()

    try:
        response = await client.post(
            f"{BASE_URL}/applications/submit",
            json=make_submission_payload(job_id),
            timeout=10.0,
        )
        result.submit_latency_ms = (time.monotonic() - t_start) * 1000

        if response.status_code == 202:
            result.submit_success = True
            data = response.json()
            result.application_id = data.get("data", {}).get("application_id")
        else:
            result.submit_error = f"HTTP {response.status_code}: {response.text[:200]}"

    except Exception as exc:
        result.submit_latency_ms = (time.monotonic() - t_start) * 1000
        result.submit_error = str(exc)

    return result


async def poll_until_terminal(
    client: httpx.AsyncClient,
    application_id: str,
    submit_time: float,
) -> tuple[str, float, int]:
    """
    Poll the status endpoint until the application reaches a terminal state.
    Returns (final_status, processing_time_ms, poll_attempts).
    """
    terminal_statuses = {"applied", "failed", "duplicate", "limit_exceeded", "expired"}
    poll_attempts = 0
    deadline = time.monotonic() + MAX_POLL_SECONDS

    while time.monotonic() < deadline:
        poll_attempts += 1
        try:
            response = await client.get(
                f"{BASE_URL}/applications/{application_id}/status",
                timeout=5.0,
            )
            if response.status_code == 200:
                status = response.json().get("data", {}).get("status", "unknown")
                if status in terminal_statuses:
                    elapsed_ms = (time.monotonic() - submit_time) * 1000
                    return status, elapsed_ms, poll_attempts
        except Exception:
            pass

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return "timeout", (time.monotonic() - submit_time) * 1000, poll_attempts


async def run_single_submission(client: httpx.AsyncClient) -> SubmitResult:
    """Submit and poll one application end-to-end."""
    job_id = str(uuid.uuid4())
    submit_time = time.monotonic()

    result = await submit_one(client, job_id)

    if result.submit_success and result.application_id:
        final_status, processing_ms, polls = await poll_until_terminal(
            client, result.application_id, submit_time
        )
        result.final_status = final_status
        result.processing_time_ms = processing_ms
        result.poll_attempts = polls

    return result


async def run_load_test(count: int, concurrency: int) -> LoadTestReport:
    """Run the full load test with the specified concurrency."""
    report = LoadTestReport()
    report.started_at = datetime.now(UTC).isoformat()

    semaphore = asyncio.Semaphore(concurrency)
    test_start = time.monotonic()

    async def bounded_submission(client: httpx.AsyncClient, idx: int) -> SubmitResult:
        async with semaphore:
            return await run_single_submission(client)

    async with httpx.AsyncClient() as client:
        # First: verify the server is up
        try:
            health = await client.get(f"{BASE_URL}/health", timeout=5.0)
            if health.status_code != 200:
                print(f"❌ Server health check failed: {health.status_code}")
                return report
            print(f"✅ Server is healthy — starting load test")
            print(f"   Target: {count} submissions, concurrency: {concurrency}")
        except Exception as exc:
            print(f"❌ Cannot reach server at {BASE_URL}: {exc}")
            print("   Make sure to run: docker-compose up --build")
            return report

        # Run submissions
        tasks = [bounded_submission(client, i) for i in range(count)]

        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            report.add_result(result)
            completed += 1

            if completed % 10 == 0 or completed == count:
                success_rate = report.successful_submits / max(completed, 1) * 100
                print(f"  Progress: {completed}/{count} ({success_rate:.0f}% success)")

    report.total_elapsed_seconds = time.monotonic() - test_start
    report.completed_at = datetime.now(UTC).isoformat()
    return report


# ── CLI entry point ────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Phase A.5 Load Test")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT,
                        help=f"Number of submissions (default: {DEFAULT_COUNT})")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"Concurrent requests (default: {DEFAULT_CONCURRENCY})")
    parser.add_argument("--output", type=str, default=None,
                        help="Save results to JSON file")
    args = parser.parse_args()

    print(f"\n🚀 Phase A.5 Load Test")
    print(f"   URL:         {BASE_URL}")
    print(f"   Submissions: {args.count}")
    print(f"   Concurrency: {args.concurrency}")

    report = await run_load_test(args.count, args.concurrency)
    report.print_summary()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(asdict(report), f, indent=2)
        print(f"\n  Results saved to: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
