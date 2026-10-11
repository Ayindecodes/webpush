# WEB X-RAY

Autonomous website investigation, testing, and diagnostics. Give WEB X-RAY an
authorized website; it explores it in an isolated browser, creates a test
account when approved, runs user journeys on desktop and mobile, records
evidence, diagnoses failures from that evidence, generates a Playwright
reproduction test, and **executes it** before calling anything reproduced.

- Product spec: [`docs/SPEC.md`](docs/SPEC.md) · UI brief: [`docs/DESIGN.md`](docs/DESIGN.md)
- Architecture and security model: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- What works today, what doesn't, and next steps: [`docs/STATUS.md`](docs/STATUS.md)

## Repository layout

```
backend/     FastAPI control plane, job queue, Playwright worker, diagnosis engine (Python 3.12)
web/         Dashboard (Next.js 16, TypeScript, Tailwind v4)
runner/      Isolated Node environment that executes generated Playwright tests
demo-shop/   Northwind Supply — benchmark app with labelled defects (defects.json)
infra/       Local Postgres init
docs/        Spec, design brief, architecture, status
```

## Prerequisites

Docker, Python 3.12, Node.js 20+.

## Setup

```bash
cp .env.example .env                      # dev defaults; secrets are required in production
docker compose up -d                      # Postgres :55432, Redis :56379

cd backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"     # (Linux/macOS: .venv/bin/pip)
.venv/Scripts/python -m playwright install chromium
.venv/Scripts/alembic upgrade head

cd ../runner && npm install               # Playwright 1.63 for generated tests
cd ../web && npm install
```

## Run (four processes)

```bash
# 1. Benchmark target (optional; allowlisted in .env for local use only)
DEMO_ALLOW_RESET=1 backend/.venv/Scripts/python -m uvicorn app:app --app-dir demo-shop --port 4100

# 2. API
cd backend && .venv/Scripts/python -m uvicorn webxray.api.app:app --port 8000

# 3. Worker (runs investigations and test executions)
cd backend && .venv/Scripts/python -m webxray.worker.main

# 4. Dashboard
cd web && npm run dev                     # http://localhost:3000
```

Then: create an account → create a project → add `http://127.0.0.1:4100` as a
target → verify (operator allowlist) → start an investigation with account
creation and sandbox orders approved.

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest tests                    # 72 tests; e2e needs the demo shop on :4100
.venv/Scripts/python -m pytest tests -m "not e2e"       # without the demo shop
.venv/Scripts/python scripts/ui_smoke.py --email ... --password ...   # every screen, desktop + mobile
cd ../web && npx tsc --noEmit && npx eslint src && npx next build
```

The test suite uses a separate `webxray_test` database (created by `infra/postgres/init.sql`).

## Configuration

All settings are `WEBXRAY_*` environment variables; see [`.env.example`](.env.example) and
`backend/webxray/config.py`. In `production` the API refuses to start with the development
secret or credential-encryption keys, or with insecure cookies.
