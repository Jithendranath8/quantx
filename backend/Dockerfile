# ======================================================================
# QuantX Backend — Multi-stage Dockerfile
# ======================================================================

# ----- Base stage -----
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# build-essential is only needed to compile wheels; it is dropped again so the
# final image does not ship a C toolchain.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ----- Development stage -----
FROM base AS development

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ----- Production stage -----
FROM base AS production

RUN apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY . .

RUN addgroup --system quantx && \
    adduser --system --ingroup quantx quantx && \
    mkdir -p /app/logs && \
    chown -R quantx:quantx /app

USER quantx

EXPOSE 8000

# Worker count is configurable rather than hardcoded: each worker holds its own
# database pool, so this number multiplies total PostgreSQL connections.
ENV BACKEND_WORKERS=4

# Apply migrations on startup, then launch the server. Running `alembic upgrade
# head` here (not only as a platform-specific pre-deploy hook) means the schema
# is created on any host — some PaaS providers silently skip their pre-deploy
# step. It is idempotent: a no-op once the DB is already at head. Single replica
# only; if you scale out, move this back to a dedicated one-shot release step.
#
# --proxy-headers lets uvicorn read the real client IP from X-Forwarded-For, but
# ONLY from peers in FORWARDED_ALLOW_IPS. That header is client-controlled, so
# trusting it from everyone ('*') let any caller spoof their IP and defeat the
# per-IP auth rate limiter / forge audit IPs. It therefore defaults to
# 127.0.0.1 (trust nothing by default); set FORWARDED_ALLOW_IPS to your real
# edge/proxy address(es) when the platform's load balancer sets XFF.
# Bind to $PORT when the platform provides one (Railway, Cloud Run, Fly, …);
# fall back to 8000 for docker-compose. Scale-to-zero free tiers are happiest
# with a single worker, so BACKEND_WORKERS defaults low and stays configurable.
ENV FORWARDED_ALLOW_IPS=127.0.0.1
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${BACKEND_WORKERS} --loop uvloop --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS}\""]
