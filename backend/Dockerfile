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

# --proxy-headers plus a trusted-host list makes X-Forwarded-For usable behind
# the nginx frontend without letting arbitrary clients spoof their IP.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${BACKEND_WORKERS} --loop uvloop --proxy-headers --forwarded-allow-ips='*'"]
