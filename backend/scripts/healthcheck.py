"""
scripts/healthcheck.py — Deployment Preflight Validation

Runs a comprehensive health check across all system components:
  1. PostgreSQL connectivity + migration state
  2. Redis connectivity + broker availability
  3. RBAC roles seeded and correct
  4. Chrome binary availability (worker environments only)
  5. Celery broker reachability

Exit codes:
  0 — all checks passed
  1 — one or more checks failed

Usage:
  # Full check (all components)
  python scripts/healthcheck.py

  # Skip Chrome check (for API containers without Chrome)
  python scripts/healthcheck.py --no-chrome

  # JSON output (for automated systems / monitoring)
  python scripts/healthcheck.py --json

  # Quick liveness check (DB + Redis only, fastest)
  python scripts/healthcheck.py --liveness
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime, UTC
from typing import Any

# Ensure project root is in PYTHONPATH
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

try:
    from app.core.config import get_settings
    settings = get_settings()
    _settings_loaded = True
except Exception as e:
    _settings_loaded = False
    _settings_error = str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Result container
# ─────────────────────────────────────────────────────────────────────────────

class CheckResult:
    def __init__(self, name: str):
        self.name = name
        self.passed: bool = False
        self.message: str = ""
        self.details: dict[str, Any] = {}
        self.duration_ms: float = 0.0

    def ok(self, message: str, **details) -> "CheckResult":
        self.passed = True
        self.message = message
        self.details = details
        return self

    def fail(self, message: str, **details) -> "CheckResult":
        self.passed = False
        self.message = message
        self.details = details
        return self

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
            "duration_ms": round(self.duration_ms, 2),
        }


def timed(fn, result: CheckResult):
    """Run fn(), record wall-clock duration on result."""
    start = time.monotonic()
    try:
        fn(result)
    finally:
        result.duration_ms = (time.monotonic() - start) * 1000


# ─────────────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────────────

def check_settings(result: CheckResult):
    if not _settings_loaded:
        result.fail(f"Settings failed to load: {_settings_error}")
        return
    result.ok(
        "Settings loaded successfully",
        app_env=settings.app_env,
        app_version=settings.app_version,
    )


def check_postgres(result: CheckResult):
    if not _settings_loaded:
        result.fail("Skipped — settings not loaded")
        return
    try:
        from sqlalchemy import create_engine, text

        # Use psycopg2 (sync) for healthcheck simplicity
        db_url = settings.database_url.replace("+asyncpg", "+psycopg2")
        engine = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            # Check alembic_version table exists and has a head revision
            try:
                rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                result.ok(
                    "PostgreSQL connected, migrations applied",
                    pg_version=version.split()[1] if version else "unknown",
                    alembic_head=rev,
                )
            except Exception:
                result.fail(
                    "PostgreSQL connected but alembic_version table missing — migrations not run",
                    pg_version=version.split()[1] if version else "unknown",
                )
        engine.dispose()
    except Exception as e:
        result.fail(f"PostgreSQL connection failed: {e}")


def check_rbac_seeded(result: CheckResult):
    if not _settings_loaded:
        result.fail("Skipped — settings not loaded")
        return
    try:
        from sqlalchemy import create_engine, text

        db_url = settings.database_url.replace("+asyncpg", "+psycopg2")
        engine = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        required_roles = {"admin", "operator", "auditor", "viewer"}
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT name FROM roles")).fetchall()
            found_roles = {row[0] for row in rows}
            missing = required_roles - found_roles
            perm_count = conn.execute(text("SELECT COUNT(*) FROM permissions")).scalar()
            role_perm_count = conn.execute(text("SELECT COUNT(*) FROM role_permissions")).scalar()
        engine.dispose()

        if missing:
            result.fail(
                f"RBAC incomplete — missing roles: {', '.join(sorted(missing))}",
                found_roles=sorted(found_roles),
                missing_roles=sorted(missing),
            )
        else:
            result.ok(
                "RBAC seeded correctly",
                roles=sorted(found_roles),
                permissions=perm_count,
                role_permission_assignments=role_perm_count,
            )
    except Exception as e:
        result.fail(f"RBAC check failed: {e}")


def check_redis(result: CheckResult):
    if not _settings_loaded:
        result.fail("Skipped — settings not loaded")
        return
    try:
        import redis as redis_lib

        client = redis_lib.from_url(settings.redis_url, socket_connect_timeout=5)
        pong = client.ping()
        info = client.info("server")
        client.close()

        if pong:
            result.ok(
                "Redis connected and responding",
                redis_version=info.get("redis_version", "unknown"),
                uptime_seconds=info.get("uptime_in_seconds", 0),
            )
        else:
            result.fail("Redis ping returned falsy response")
    except Exception as e:
        result.fail(f"Redis connection failed: {e}")


def check_celery_broker(result: CheckResult):
    if not _settings_loaded:
        result.fail("Skipped — settings not loaded")
        return
    try:
        import redis as redis_lib

        broker_url = getattr(settings, "celery_broker_url", None)
        if not broker_url:
            result.fail("CELERY_BROKER_URL not configured")
            return

        # Parse redis://host:port/db from broker URL
        client = redis_lib.from_url(broker_url, socket_connect_timeout=5)
        pong = client.ping()
        client.close()

        if pong:
            result.ok("Celery broker (Redis) reachable", broker_url=broker_url.rsplit("/", 1)[0])
        else:
            result.fail("Celery broker ping failed")
    except Exception as e:
        result.fail(f"Celery broker check failed: {e}")


def check_chrome(result: CheckResult):
    """
    Verify Chrome is installed and the version matches CHROME_VERSION env var.
    Only meaningful in worker containers.
    """
    chrome_bin = os.environ.get("CHROME_BIN", "google-chrome-stable")
    expected_version = os.environ.get("CHROME_VERSION", "")

    try:
        proc = subprocess.run(
            [chrome_bin, "--version", "--no-sandbox"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            result.fail(
                f"Chrome returned non-zero exit code {proc.returncode}",
                stderr=proc.stderr.strip(),
            )
            return

        chrome_version_str = proc.stdout.strip()
        # Output: "Google Chrome 131.0.6778.204 ..."
        installed_version = chrome_version_str.split()[-1] if chrome_version_str else "unknown"

        if expected_version and not installed_version.startswith(expected_version.split("-")[0]):
            result.fail(
                f"Chrome version mismatch — expected {expected_version}, got {installed_version}",
                installed=installed_version,
                expected=expected_version,
            )
        else:
            result.ok(
                "Chrome available and version matches",
                installed_version=installed_version,
                expected_version=expected_version or "not pinned",
            )
    except FileNotFoundError:
        result.fail(
            f"Chrome binary not found at '{chrome_bin}' — is this a worker container?",
            chrome_bin=chrome_bin,
        )
    except subprocess.TimeoutExpired:
        result.fail("Chrome --version timed out after 10s")
    except Exception as e:
        result.fail(f"Chrome check failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_checks(
    skip_chrome: bool = False,
    liveness_only: bool = False,
) -> tuple[list[CheckResult], bool]:
    """
    Run all health checks. Returns (results, all_passed).

    liveness_only: only DB + Redis ping (fastest — suitable for Docker HEALTHCHECK)
    skip_chrome:   skip Chrome binary check (for API containers)
    """
    checks_to_run = []

    # Always run settings
    r = CheckResult("settings")
    timed(check_settings, r)
    checks_to_run.append(r)

    # PostgreSQL
    r = CheckResult("postgres")
    timed(check_postgres, r)
    checks_to_run.append(r)

    # Redis
    r = CheckResult("redis")
    timed(check_redis, r)
    checks_to_run.append(r)

    if not liveness_only:
        # RBAC seed state
        r = CheckResult("rbac_seeded")
        timed(check_rbac_seeded, r)
        checks_to_run.append(r)

        # Celery broker
        r = CheckResult("celery_broker")
        timed(check_celery_broker, r)
        checks_to_run.append(r)

        # Chrome (optional)
        if not skip_chrome:
            r = CheckResult("chrome")
            timed(check_chrome, r)
            checks_to_run.append(r)

    all_passed = all(r.passed for r in checks_to_run)
    return checks_to_run, all_passed


# ─────────────────────────────────────────────────────────────────────────────
# Output formatters
# ─────────────────────────────────────────────────────────────────────────────

PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"


def print_human(results: list[CheckResult], all_passed: bool):
    print()
    print("=" * 60)
    print("  Application Automation Agent -- Health Check")
    print(f"  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)
    for r in results:
        status = PASS if r.passed else FAIL
        print(f"  {status}  {r.name:<20} {r.message}  ({r.duration_ms:.0f}ms)")
        if not r.passed and r.details:
            for k, v in r.details.items():
                print(f"           {k}: {v}")
    print("=" * 60)
    overall = "\033[32mOVERALL: HEALTHY\033[0m" if all_passed else "\033[31mOVERALL: UNHEALTHY\033[0m"
    print(f"  {overall}")
    print()


def print_json_output(results: list[CheckResult], all_passed: bool):
    output = {
        "timestamp": datetime.now(UTC).isoformat(),
        "overall": "healthy" if all_passed else "unhealthy",
        "checks": [r.to_dict() for r in results],
    }
    print(json.dumps(output, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Application Automation Agent — deployment health check"
    )
    parser.add_argument(
        "--no-chrome",
        action="store_true",
        help="Skip Chrome binary check (use in API containers without Chrome)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON (for monitoring systems)",
    )
    parser.add_argument(
        "--liveness",
        action="store_true",
        help="Quick liveness check: DB + Redis only. Suitable for Docker HEALTHCHECK CMD.",
    )
    args = parser.parse_args()

    results, all_passed = run_checks(
        skip_chrome=args.no_chrome,
        liveness_only=args.liveness,
    )

    if args.json_output:
        print_json_output(results, all_passed)
    else:
        print_human(results, all_passed)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
