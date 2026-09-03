#!/usr/bin/env bash
# QuantX — run the backend test suite.
#
# Tests need an isolated environment. Reusing the live one makes them fail for
# reasons that have nothing to do with the code:
#   * the running app's rate-limit counters live in Redis and return 429
#   * MARKET_STREAM_ENABLED=true breaks tests asserting the default is off
#   * a configured AI provider breaks tests asserting "not configured"
# So real credentials come from .env, and everything the tests assert about is
# overridden back to its default here.
#
# Usage:  ./run-tests.sh [pytest args...]
#         ./run-tests.sh tests/unit -k leader
set -euo pipefail
cd "$(dirname "$0")"

NETWORK="ai-trading-research-platform_default"
IMAGE="quantx-backend:dev"

# The dev stage carries pytest; the production image deliberately does not.
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "building $IMAGE (test dependencies)..."
  docker build --target development -t "$IMAGE" backend/
fi

PW="$(grep -E '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)"

# Created once; the suite truncates between tests but does not create the DB.
docker exec quantx-postgres psql -U quantx -d postgres \
  -c "CREATE DATABASE quantx_test OWNER quantx;" >/dev/null 2>&1 || true

exec docker run --rm --network "$NETWORK" \
  --env-file .env \
  -v "$PWD/backend:/app" -w /app \
  -e POSTGRES_HOST=postgres \
  -e REDIS_HOST=redis \
  -e REDIS_DB=9 \
  -e OPENAI_API_KEY= -e OPENAI_BASE_URL= -e OPENAI_MODEL= \
  -e MARKET_STREAM_ENABLED=false \
  -e RATE_LIMIT_ENABLED=false \
  -e TEST_DATABASE_URL="postgresql+asyncpg://quantx:${PW}@postgres:5432/quantx_test" \
  "$IMAGE" python -m pytest "${@:-tests/}" -q -p no:randomly
