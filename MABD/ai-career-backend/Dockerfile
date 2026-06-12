# ================= Stage 1: Build Stage =================
FROM python:3.13-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install building tools required for compiling C extensions like psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install dependencies into user directory
RUN pip install --no-cache-dir --user -r requirements.txt


# ================= Stage 2: Runner Stage =================
FROM python:3.13-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

# Install PostgreSQL runtime client library needed by psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed dependencies and project source code
COPY --from=builder /root/.local /root/.local
COPY . .

# Expose backend port
EXPOSE 8000

# Run FastAPI app with Uvicorn in production mode
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
