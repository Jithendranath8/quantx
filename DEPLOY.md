# Deploying QuantX for free

A practical, **$0** way to put QuantX online for a portfolio demo. No single
free tier hosts the whole stack (API + Postgres + Redis + an always-on worker),
so we split it across free tiers and replace the Celery worker with a free cron.

> Honest expectations: free API tiers **sleep when idle** and cold-start in
> ~30–60s. Managed free Postgres/Redis are small and may require periodic
> keep-alive. The deep-learning ML extra is **not** deployed (it's optional and
> heavy) — train models offline and the agent simply runs without the ML signal.

## Architecture

| Layer | Service | Free? |
|---|---|---|
| Frontend (static SPA) | **Cloudflare Pages** (or Render static) | Yes |
| API (FastAPI, Docker) | **Render** web service (or Fly.io / Cloud Run) | Yes |
| PostgreSQL | **Neon** | Yes |
| Redis (cache/rate-limit) | **Upstash** (TLS `rediss://`) | Yes |
| Scheduled jobs | **GitHub Actions cron** → `/api/v1/internal/jobs/*` | Yes |
| ML (torch/TF) | not deployed — train offline | n/a |

The app already supports this: it reads a single `DATABASE_URL` / `REDIS_URL`
(scheme normalized for asyncpg; TLS Redis supported), binds to `$PORT`, and
exposes a secret-gated cron endpoint so no background worker is needed.

## Steps

### 1. PostgreSQL — Neon
1. Create a project at neon.tech (no card). Copy the connection string
   (`postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`).
2. You'll paste it as `DATABASE_URL`. The app rewrites it to asyncpg and keeps
   `sslmode` for migrations automatically.

### 2. Redis — Upstash
1. Create a Redis database at upstash.com (no card). Copy the **`rediss://`**
   (TLS) URL — you'll paste it as `REDIS_URL`.

### 3. API — Render
1. Generate secrets:
   ```bash
   python3 -c "import secrets; [print(f'{k}={secrets.token_urlsafe(48)}') for k in ('SECRET_KEY','JWT_SECRET_KEY','CRON_SECRET')]"
   ```
2. New → **Blueprint** and pick this repo (uses [`render.yaml`](render.yaml)), or
   create a **Web Service** manually: Runtime **Docker**, Dockerfile
   `backend/Dockerfile`, context `backend`, Plan **Free**.
3. Set **pre-deploy command** to `alembic upgrade head` (runs migrations).
4. Add environment variables from [`.env.deploy.example`](.env.deploy.example):
   `APP_ENV=production`, `DEBUG=false`, `BACKEND_WORKERS=1`,
   `SECRET_KEY`, `JWT_SECRET_KEY`, `CRON_SECRET`, `DATABASE_URL`, `REDIS_URL`,
   `ALLOWED_ORIGINS` (your frontend URL), and a free AI provider
   (`OPENAI_BASE_URL`/`OPENAI_MODEL`/`OPENAI_API_KEY` for Groq/Gemini, or
   `ANTHROPIC_API_KEY`). Keep `BINANCE_TESTNET=true`,
   `ALLOW_MAINNET_TRADING=false`, `MARKET_STREAM_ENABLED=false`.
5. Deploy. Note the public URL, e.g. `https://quantx-api.onrender.com`.

### 4. Frontend — Cloudflare Pages
1. New Pages project from this repo. Build command `npm ci && npm run build`,
   output dir `frontend/dist`, root `frontend`.
2. Set a build env var **`VITE_API_BASE_URL`** = `https://quantx-api.onrender.com/api/v1`
   (the API URL from step 3 + `/api/v1`). The SPA falls back to the same-origin
   `/api/v1` when this is unset (the nginx/docker-compose path), so this var is
   what makes the split deploy work.
3. Deploy, then set the API's `ALLOWED_ORIGINS` to the Pages URL and redeploy the
   API so CORS allows the browser.

### 5. Scheduled jobs — GitHub Actions
The workflow [`.github/workflows/scheduled-jobs.yml`](.github/workflows/scheduled-jobs.yml)
pokes the API's cron endpoint every 5 minutes (and nightly). Add two **repo
secrets** (Settings → Secrets → Actions):
- `DEPLOY_URL` = `https://quantx-api.onrender.com`
- `CRON_SECRET` = the same value you set on the API

Trigger it once from the Actions tab (**Run workflow**) to confirm. Each job
returns `{"job": ..., "result": ...}`; a `401` means the secret mismatches, a
`503` means `CRON_SECRET` isn't set on the API.

### 6. Verify
- `GET https://quantx-api.onrender.com/docs` is disabled in production; instead
  register/login from the frontend and exercise a page.
- Run the agent: `POST /api/v1/agent/orchestrate?symbol=BTCUSDT` (needs an AI
  provider configured, else `503`).

## Caveats & alternatives
- **Idle sleep:** Render free sleeps after ~15 min. The 5-min cron keeps it
  warmer but not always-on. Acceptable for a demo.
- **Always-on worker / ML inference:** if you want real background processing or
  live ML predictions, use **Fly.io** — its allowance can run the API *and* a
  small Celery worker (`celery -A app.core.celery_app worker --beat`) as a
  second process, and you can install the `[ml]` extra in that image (CPU torch:
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`).
- **Databases don't expire with Neon/Upstash;** Render's own free datastores are
  more limited, which is why we use the managed ones.
