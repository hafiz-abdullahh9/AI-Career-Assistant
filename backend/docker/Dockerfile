# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: dependency builder
# Separates pip install from the runtime image so changes to app code do not
# invalidate the (expensive) dependency layer.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12.4-slim AS builder

LABEL stage="builder"

# Prevent .pyc files and enable unbuffered stdout/stderr for Docker log shipping
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build-time system deps (gcc, libpq-dev needed to compile psycopg2-binary)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy dependency manifests first — maximises Docker layer cache reuse.
# Re-installs only when pyproject.toml or requirements.txt changes, NOT on
# every code change. Both files are included so the lockfile is auditable
# inside the image layer.
COPY pyproject.toml ./
COPY requirements.txt ./

# Non-editable, deterministic install into an isolated prefix.
# ensures no .pth or editable install artefacts are created.
RUN pip install --upgrade pip \
    && pip install --prefix=/install .


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: production runtime
# Minimal image — no build tools, no compilers, no dev artefacts.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12.4-slim AS production

LABEL maintainer="Member 4 — Application Automation Agent" \
      version="1.0.0" \
      description="AI Career Assistant — FastAPI application server"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/install/bin:$PATH" \
    # Tell Python to find packages installed in /install
    PYTHONPATH="/install/lib/python3.12/site-packages:/app"

# Runtime-only system dependencies (curl for HEALTHCHECK, libpq for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Security: run as a non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy pre-built packages from the builder stage
COPY --from=builder /install /install

WORKDIR /app

# Copy application source, migrations, config, and operational scripts
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY alembic.ini ./

# Ensure the non-root user owns everything
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8004

# Health check: waits up to 20s for startup, then probes every 30s
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

# Production default: no --reload; concurrency configured via env/compose
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004", \
     "--workers", "2", "--loop", "asyncio"]
