# ================= Stage 1: Build Stage =================
FROM python:3.13-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install build tools required for compiling C extensions like psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install all dependencies + gunicorn (production WSGI server for Django)
RUN pip install --no-cache-dir --user -r requirements.txt gunicorn==22.0.0


# ================= Stage 2: Runner Stage =================
FROM python:3.13-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH \
    DJANGO_SETTINGS_MODULE=career_assistant.settings

# Install PostgreSQL runtime client library needed by psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed dependencies and project source code
COPY --from=builder /root/.local /root/.local
COPY . .

# Collect static files for Django Admin
RUN python manage.py collectstatic --noinput || true

# Expose backend port
EXPOSE 8000

# Run Django migrations automatically, then start Gunicorn (production WSGI)
# --workers 3: good default for small servers (2*CPU + 1)
# --timeout 120: allow slow LLM API calls to complete
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn career_assistant.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120"]
