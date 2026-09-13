# Fixpoint

A multi-app agent (billing, inbox, CRM, chat, docs) that resolves customer exceptions and
**proves** it. The LLM proposes; deterministic code authorizes; a human approves money; an
independent verifier re-reads real state before the agent is allowed to claim success.

This repository is a production-ready build of `docs/fixpoint-plan.html`:

- **Backend** — Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Alembic
- **Frontend** — React 18, Vite, TypeScript, Tailwind CSS (dark run console + evaluation dashboard)
- **Agent** — deterministic quarantine parser and planner by default, plus an optional LLM planner
  (OpenAI-compatible) behind the same gateway. Every LLM error falls back to the deterministic
  planner, so runs stay replayable with no API key required.
- **Providers** — in-process deterministic twins by default, or Arga digital twins over HTTP for
  Stripe, Gmail, Slack, HubSpot and Google Drive (`FIXPOINT_PROVIDER_BACKEND=arga`).
- **Safety core** — Action Gateway, HMAC approvals, hash-chained audit log, independent verifier
- **Evaluation** — the S1–S16 security & reliability matrix with a PASS / FAIL / unsafe-blocked scoreboard

---

## Safety model

1. **Untrusted by default.** Request text, provider data and model output are data, never
   instructions. The quarantine parser (tools disabled) turns text into strict facts and flags
   injections.
2. **Sealed context.** Tenant, actor, capabilities and the amount envelope are assembled
   server-side in a `RunContext`. The model can never name a tenant or change authority.
3. **Deny-by-default gateway.** The Action Gateway is the only mutation path. Checks run in a
   fixed order: tool allow-list → capability grant → tenant binding → forbidden ops → data guard →
   field allow-list → destination/charge pinning → velocity → idempotency → amount cap → approval.
4. **Bound human approvals.** Money above the envelope pauses. The approval artifact is built from
   source-of-truth provider state (never the model's narrative) and the token is HMAC-signed,
   single-use, expiring, and bound to one `action_hash`. Any change voids it.
5. **Independent verification.** After every mutation the verifier re-reads provider state and
   asserts required outcomes, forbidden side effects and cross-system sync. Claims that cannot be
   grounded fail the run — the agent never reports success it cannot prove.
6. **Tamper-evident audit.** Every plan, proposal, gateway decision, tool call, mutation, approval
   and verification is appended to a hash-chained ledger. Breaking one entry is detectable at the
   exact index.

Approval envelope (configurable via environment):

| Amount | Behavior |
| --- | --- |
| ≤ $25 | autonomous |
| ≤ $250 | team-lead approval |
| ≤ $2,500 | finance approval |
| > $2,500 or over cap | dual approval + separation of duties |

---

## Architecture

```
request text ──▶ quarantine parser ──▶ planner ──▶ ProposedAction
                                                        │
                                       sealed RunContext ▼
                                              ┌────────────────────┐
                                              │   Action Gateway   │  deny-by-default
                                              └─────────┬──────────┘
                                    ALLOW               │            REQUIRE_APPROVAL / REJECT
                        ┌───────────────────────────────┤            ┌──────────────────────┐
                        ▼                               │            ▼                      ▼
              tenant-scoped adapters                    │   approval artifact        unsafe-blocked
                        │                               │   (human approves/denies)  audit entry
                        ▼                               │            │
              provider twins (Stripe, Gmail,            │            ▼
              Slack, CRM, Drive) ───────────────────────┴──── bound, single-use token
                        │
                        ▼
              independent verifier ──▶ hash-chained audit log ──▶ report
```

---

## Repository layout

```
backend/
  app/
    agent/           parser, planner, LLM planner + fallback, run engine (untrusted side)
    safety/          gateway, approval, audit, canonical, webhooks, verifier (the product)
    providers/       in-process twins, Arga digital-twin backend, tenant-scoped adapters
    evals/           S1-S16 scenarios and runner
    routers/         FastAPI routers (runs, scenarios, evals, webhooks, health, config)
    repository/      database access layer
    services/        run lifecycle orchestration + committed-plan approval replay
  scripts/           arga_provision.py (provision Arga twins, emit env)
  alembic/           migrations (run automatically on container start)
  tests/             60+ deterministic unit, API, DB, replay and adapter tests
frontend/
  src/               React console: Run Console, Evaluation, Runs, Run Detail, About
Dockerfile           multi-stage: Node build -> Python runtime serving API + SPA
railway.json         Railway deploy configuration (healthcheck /health)
docker-compose.yml   local Postgres + API
docs/                original design document
```

---

## Quickstart

### Option A — Docker (one command, includes Postgres)

```bash
docker compose up --build
# open http://localhost:8000
```

The container runs Alembic migrations, then serves the API, the SPA and `/docs`.

### Option B — local development

Backend (SQLite by default, zero setup):

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements-dev.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Frontend (proxies `/api` and `/health` to port 8000):

```bash
cd frontend
npm install
npm run dev
# open http://localhost:5173
```

### Tests and evaluations

```bash
cd backend
python -m pytest -q          # 60+ tests
python -m app.evals.runner   # S1-S16 matrix, 16/16 PASS expected
python -m ruff check .       # lint
```

### Enable the LLM planner (optional)

Fixpoint runs with the deterministic planner by default. To use an LLM (any OpenAI-compatible
endpoint), set `FIXPOINT_LLM_ENABLED=true` plus `FIXPOINT_LLM_BASE_URL`, `FIXPOINT_LLM_API_KEY`
and `FIXPOINT_LLM_MODEL`. Any model error, timeout or schema violation falls back to the
deterministic planner automatically (`planner_source` shows `llm` or `llm_fallback`).

A local mock is included so you can demo/test the wiring with no keys:

```bash
cd backend
python -m scripts.mock_llm_server --port 8123     # shell 1
# shell 2:
FIXPOINT_LLM_ENABLED=true \
FIXPOINT_LLM_BASE_URL=http://localhost:8123/v1 \
FIXPOINT_LLM_API_KEY=mock \
FIXPOINT_LLM_MODEL=mock-llm \
python -m uvicorn app.main:app --port 8000
```

See [`docs/DEPLOY.md`](docs/DEPLOY.md) for real providers, Railway deployment and Postgres.

---

## API reference

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness + database probe (Railway healthcheck) |
| `GET` | `/api/config` | Demo mode, envelope thresholds, version |
| `POST` | `/api/runs` | Run the agent end to end; returns full timeline |
| `GET` | `/api/runs` | Run history (persisted in Postgres) |
| `GET` | `/api/runs/{id}` | Full run detail with verified audit chain |
| `POST` | `/api/runs/{id}/approve` | Apply a bound human approval |
| `POST` | `/api/runs/{id}/deny` | Deny the pending action; reconcile records |
| `GET` | `/api/runs/{id}/audit` | Audit entries + chain verification |
| `POST` | `/api/runs/{id}/audit/tamper` | Demo-only: break the chain to prove detection |
| `GET` | `/api/scenarios` | List S1–S16 |
| `POST` | `/api/scenarios/{id}/run` | Run one scenario |
| `POST` | `/api/evals/run` | Run the full matrix and persist results |
| `GET` | `/api/evals/results` | Latest stored batch (survives restarts) |
| `POST` | `/api/webhooks/{provider}` | HMAC-verified, replay-protected webhooks |

Interactive docs: `/docs`.

---

## Demo script (2 minutes)

1. **Problem (0:15)** — one refund takes 20 minutes across five apps.
2. **Benign run (1:00)** — submit the “Double charge” preset for **$42**:
   investigation → gateway requires approval → facts and sealed action hash shown → approve →
   idempotent refund + CRM note + Slack audit + Gmail draft (never sent) → verifier passes.
3. **Recovery (0:20)** — tick **Inject Stripe 500**, run again: detect → retry with the same
   idempotency key → exactly one refund exists.
4. **Refusal (0:15)** — use **Injection $2,000**: refused by the gateway, logged as unsafe-blocked,
   escalation artifact created, zero money moved.
5. **Proof (0:10)** — Evaluation tab: 16/16 PASS, zero unsafe mutations, unsafe-blocked events
   visible; press **Tamper** on the audit chain to show detection.

---

## Deploy to Railway

1. Push this repository to GitHub.
2. In Railway: **New Project → Deploy from GitHub repo** and pick the repository.
   Railway reads `railway.json` and builds the `Dockerfile` (Node build stage + Python runtime).
3. **Add PostgreSQL**: in the project canvas click **New → Database → PostgreSQL**.
   Railway injects `DATABASE_URL` into the service; the app normalizes `postgres://` to the async
   driver automatically.
4. **Set service variables** (Settings → Variables):

   | Variable | Value |
   | --- | --- |
   | `FIXPOINT_SIGNING_KEY` | strong random string (required) |
   | `FIXPOINT_WEBHOOK_SECRET` | strong random string (required) |
   | `FIXPOINT_ENV` | `production` |
   | `FIXPOINT_DEMO_MODE` | `true` for the hackathon demo, `false` otherwise |

   Generate secrets with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
5. **Generate a domain**: Settings → Networking → Generate Domain.
6. Open `https://<your-domain>/` — the console is served by the same service; `/health` is the
   healthcheck and migrations run on every container start.

Notes:

- The server binds `0.0.0.0` and `$PORT` (see `backend/start.sh`); nothing is hardcoded.
- Run a **single replica** (default). Run sessions are reconstructable from the database, but the
  audit chain is appended per run and a single writer keeps the demo deterministic.
- No secrets are committed; the image logs a warning when development defaults are in use.

---

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` / `FIXPOINT_DATABASE_URL` | `sqlite+aiosqlite:///./fixpoint.db` | Async database URL (Railway injects `DATABASE_URL`) |
| `FIXPOINT_ENV` | `development` | Environment label |
| `FIXPOINT_SIGNING_KEY` | `dev-only-change-me` | HMAC key for approval tokens — **change in production** |
| `FIXPOINT_WEBHOOK_SECRET` | `dev-webhook-secret` | HMAC key for provider webhooks — **change in production** |
| `FIXPOINT_DEMO_MODE` | `true` | Enables the audit-tamper demo endpoint |
| `FIXPOINT_MAX_REFUND_CENTS` | `250000` | Hard cap; above it escalation requires dual approval |
| `FIXPOINT_AUTO_APPROVE_CENTS` | `2500` | Autonomous threshold |
| `FIXPOINT_TEAM_LEAD_CENTS` | `25000` | Team-lead approval threshold |
| `FIXPOINT_DUAL_APPROVAL_CENTS` | `250000` | Dual approval + separation-of-duties threshold |
| `FIXPOINT_MAX_ACTIONS_PER_RUN` | `20` | Velocity limit per tool per run |
| `FIXPOINT_DEFAULT_TENANT_ID` | `t_123` | Session stand-in until auth is added |
| `FIXPOINT_DEFAULT_ACTOR_USER_ID` | `u_88` | Session stand-in until auth is added |
| `FIXPOINT_LLM_ENABLED` | `false` | Enable the optional LLM parser/planner (falls back on any error) |
| `FIXPOINT_LLM_BASE_URL` | empty | OpenAI-compatible base URL (e.g. `https://api.openai.com/v1`) |
| `FIXPOINT_LLM_API_KEY` | empty | API key for the LLM endpoint |
| `FIXPOINT_LLM_MODEL` | empty | Model name (e.g. `gpt-4o-mini`) |
| `FIXPOINT_LLM_TIMEOUT_SECONDS` | `20` | Model call timeout before fallback |
| `FIXPOINT_PROVIDER_BACKEND` | `twin` | `twin` (in-process) or `arga` (digital twins over HTTP) |
| `FIXPOINT_ARGA_*_URL` / `_TOKEN` | empty | Per-service Arga twin endpoints (Stripe, Gmail, Slack, HubSpot, Drive) |
| `FIXPOINT_CORS_ORIGINS` | `http://localhost:5173,...` | Dev-server CORS (production is same-origin) |
| `FIXPOINT_STATIC_DIR` | empty | Built SPA directory (set in the Docker image) |

---

## Production roadmap

Explicitly out of scope for this hackathon build, and the first things to add next:

- Authentication and user management; tenant identity from the session, not a stand-in
- A real per-tenant secret vault (envelope encryption, rotation, short-lived provider tokens)
- Postgres row-level security and per-tenant repository filters
- Hardening the Arga backend into the default for every environment (seed + reset automation)
- Lemma tracing per run and cost/latency charts for the LLM planner
- A fifth app (Notion or Linear) and dispute evidence packet generation

---

Built for the Multi-App AI Agent Hackathon 2026. The original design document lives at
[`docs/fixpoint-plan.html`](docs/fixpoint-plan.html).
