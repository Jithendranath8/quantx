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
| Frontend (static SPA) | **Cloudflare Pages** | Yes |
| API (FastAPI, Docker) | **Railway** service (or Fly.io / Cloud Run) | Trial credit, then ~$5/mo |
| PostgreSQL | **Neon** | Yes |
| Redis (cache/rate-limit) | **Upstash** (TLS `rediss://`) | Yes |
| Scheduled jobs | **GitHub Actions cron** → `/api/v1/internal/jobs/*` | Yes |
| ML (torch/TF) | not deployed — train offline | n/a |

> **On Railway's pricing:** Railway no longer has a perpetual free tier. New
> accounts get a one-time trial credit (enough to run this small service for a
> while); after that the Hobby plan is ~$5/mo with $5 of usage included. Unlike
> Render free it does **not** sleep when idle. If you want strictly $0, Fly.io or
> Render's free web service are drop-in alternatives for the API layer.

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

### 3. API — Railway
1. Generate secrets:
   ```bash
   python3 -c "import secrets; [print(f'{k}={secrets.token_urlsafe(48)}') for k in ('SECRET_KEY','JWT_SECRET_KEY','CRON_SECRET')]"
   ```
2. Create a project at railway.app → **Deploy from GitHub repo** and pick this
   repo. In the service **Settings**:
   - **Root Directory** = `backend` (so the Dockerfile's build context is correct).
   - Railway auto-detects [`backend/railway.json`](backend/railway.json): it builds
     the Dockerfile and health-checks `/health`. The image applies `alembic upgrade
     head` on startup and binds `$PORT`, so no start or pre-deploy command is needed.
   Alternatively, headless from the CLI (from the repo root):
   ```bash
   npm i -g @railway/cli        # or: npx @railway/cli
   railway link                  # pick/create the project
   railway up --service <name>   # build + deploy backend/
   ```
3. Add environment variables (service → **Variables**):
   `APP_ENV=production`, `DEBUG=false`, `BACKEND_WORKERS=1`,
   `BINANCE_TESTNET=true`, `ALLOW_MAINNET_TRADING=false`,
   `MARKET_STREAM_ENABLED=false`, `LLM_PROVIDER=auto`,
   `SECRET_KEY`, `JWT_SECRET_KEY`, `CRON_SECRET`, `DATABASE_URL`, `REDIS_URL`,
   `ALLOWED_ORIGINS` (your frontend URL), and a free AI provider
   (`OPENAI_BASE_URL`/`OPENAI_MODEL`/`OPENAI_API_KEY` for Groq/Gemini, or
   `ANTHROPIC_API_KEY`).
4. Deploy, then under **Settings → Networking → Public Networking** click
   **Generate Domain**. Note the URL, e.g. `https://quantx-api.up.railway.app`.

### 4. Frontend — Cloudflare Pages
1. New Pages project from this repo. Build command `npm ci && npm run build`,
   output dir `frontend/dist`, root `frontend`.
2. Set a build env var **`VITE_API_BASE_URL`** = `https://quantx-api.up.railway.app/api/v1`
   (the API URL from step 3 + `/api/v1`). The SPA falls back to the same-origin
   `/api/v1` when this is unset (the nginx/docker-compose path), so this var is
   what makes the split deploy work.
3. Deploy, then set the API's `ALLOWED_ORIGINS` to the Pages URL and redeploy the
   API so CORS allows the browser.

### 5. Scheduled jobs — GitHub Actions
The workflow [`.github/workflows/scheduled-jobs.yml`](.github/workflows/scheduled-jobs.yml)
pokes the API's cron endpoint every 5 minutes (and nightly). Add two **repo
secrets** (Settings → Secrets → Actions):
- `DEPLOY_URL` = `https://quantx-api.up.railway.app`
- `CRON_SECRET` = the same value you set on the API

Trigger it once from the Actions tab (**Run workflow**) to confirm. Each job
returns `{"job": ..., "result": ...}`; a `401` means the secret mismatches, a
`503` means `CRON_SECRET` isn't set on the API.

### 6. Verify
- `GET https://quantx-api.up.railway.app/docs` is disabled in production; instead
  register/login from the frontend and exercise a page.
- Run the agent: `POST /api/v1/agent/orchestrate?symbol=BTCUSDT` (needs an AI
  provider configured, else `503`).

## Caveats & alternatives
- **Cost:** Railway is usage-based after the trial credit (~$5/mo Hobby). It does
  not sleep, so the 5-min cron is about keeping data fresh, not keeping the box
  awake. For strictly $0, swap the API layer for **Fly.io** or a **Render** free
  web service (which does sleep after ~15 min idle).
- **Always-on worker / ML inference:** the default deploy replaces the Celery
  worker with the GitHub Actions cron. If you want real background processing or
  live ML predictions, Railway can also run a **second service** for the worker
  (`celery -A app.core.celery_app worker --beat`) from the same image, and you
  can install the `[ml]` extra there (CPU torch:
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`).
- **Databases don't expire** with Neon/Upstash, which is why we use the managed
  ones rather than a host's bundled datastore.
