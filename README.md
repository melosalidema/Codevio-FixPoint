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
storefront/          Fake customer storefront (Platzi Fake Store API -> Fixpoint refunds)
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

### Demo storefront (customer side)

`storefront/` is a fake ecommerce app that exercises the agent end to end: it lists products
from the Platzi Fake Store API, creates demo orders with an immutable price snapshot, and files
refund requests into `POST /api/runs`. Small refunds complete autonomously; larger ones pause
for a human in the operator console.

```bash
cd storefront
npm install
npm run dev
# open http://localhost:5174 (proxies /api to the backend on :8000)
```

Demo tip: check out as `jane@acme.com` (the seeded customer the twins can resolve). The refund
form has *Test hooks* for Stripe-failure retries, prompt injection and ambiguous-identity
escalation. `make storefront` and `make storefront-build` wrap the same commands.

Order and refund events also send an email notification through Formspree
(`storefront/src/lib/formspree.ts`): order placements email the order summary, and refund
requests email the reason, amount and exact agent request text. Notifications are sent with the
customer's address as Reply-To and never block the order or the agent run. Set
`VITE_FORMSPREE_FORM_ID` to use a different form; the default points at the demo form.

The backend sends a second email when a refund is **decided** — autonomously by the agent or by a
human approving/denying in the console — including the decision, amount, order, run id and who
decided (`backend/app/services/notifications.py`). Enable it with
`FIXPOINT_NOTIFY_FORMSPREE_ENABLED=true` plus `FIXPOINT_NOTIFY_FORMSPREE_FORM_ID`; delivery is
best-effort and never affects the run.

### Real Stripe (test mode)

Stripe can run for real while Gmail/Slack/CRM/Drive stay on the deterministic twins:

```bash
cd backend
FIXPOINT_STRIPE_BACKEND=stripe \
FIXPOINT_STRIPE_API_KEY=sk_test_... \
python -m uvicorn app.main:app --port 8000
```

- **Seed demo data** (customer `jane@acme.com`, two identical $42 charges, optional subscription):
  `python -m scripts.stripe_seed`. The script reuses `metadata.fixpoint_seed` objects and refuses
  live keys.
- **Webhooks locally:** run `stripe listen --forward-to localhost:8000/api/webhooks/stripe` and put
  the printed `whsec_...` in `FIXPOINT_STRIPE_WEBHOOK_SECRET`. `charge.refunded`,
  `refund.created/updated/failed` and `charge.dispute.created` are signature-verified against the
  raw body (300s tolerance), deduplicated, recorded and linked to the run through
  `metadata.run_id`; mismatches are flagged rather than repaired.
- **Safety:** live keys are refused unless `FIXPOINT_STRIPE_ALLOW_LIVE=true`; charge pinning,
  amount ceilings, approval and idempotency are unchanged, and refund POSTs are only retried by
  the engine with the same persisted key.
- **Verification:** the verifier re-reads `GET /v1/charges/{id}` and `GET /v1/refunds?charge=`,
  then asserts exactly one refund totalling the approved amount before the run can report success.

### Real HubSpot CRM (private app)

HubSpot can run for real while Stripe and the other apps use their own backends:

```bash
cd backend
FIXPOINT_CRM_BACKEND=hubspot \
FIXPOINT_HUBSPOT_TOKEN=pat-... \
python -m uvicorn app.main:app --port 8000
```

- **Scopes:** `crm.objects.contacts.read`, `crm.objects.contacts.write`,
  `crm.objects.notes.read`, `crm.objects.notes.write`; add `crm.schemas.contacts.write` only when
  the seeder creates the custom status property.
- **Seed:** `python -m scripts.hubspot_seed --yes` (reuses/creates `jane@acme.com`);
  `--with-duplicate` for the ambiguity demo, `--create-status-property` to create
  `fixpoint_status`.
- **Safety:** the agent pins one contact, writes the run note **associated with that contact**
  (note→contact type 202) and, when `FIXPOINT_HUBSPOT_REFUND_STATUS` is set, patches the status
  property. Contact notes are re-read from HubSpot (`crm_note_recorded`) before the run may claim
  success — there is no cache fallback for live HubSpot.
- **Duplicate contacts:** multiple contacts for the same email trigger the same ambiguity
  escalation as duplicate Stripe customers; the agent never guesses.
- **Limitations:** HubSpot private-app tokens write to a **real portal** (there is no test mode);
  use a developer test account and treat the token as a production secret. CRM-case intake is not
  implemented in v1 — legacy private apps cannot sign webhooks; future options are polling
  (preferred) or a public OAuth app with signed webhook handling.

### Tests and evaluations

```bash
cd backend
python -m pytest -q          # 60+ tests
python -m app.evals.runner   # S1-S16 matrix, 16/16 PASS expected
python -m ruff check .       # lint
```

### Enable the LLM planner (optional)

Fixpoint runs with the deterministic planner by default. To use an LLM, set
`FIXPOINT_LLM_ENABLED=true`, a `FIXPOINT_LLM_PROVIDER`, and (for keyed providers) a key:

```bash
FIXPOINT_LLM_PROVIDER=groq          # pollinations (free/keyless), groq, gemini, github, openai, custom
FIXPOINT_LLM_API_KEY=gsk_...        # not needed for pollinations
```

Presets fill the base URL and model; override with `FIXPOINT_LLM_BASE_URL`/`FIXPOINT_LLM_MODEL`
or use `provider=custom` (LM Studio, Ollama, vLLM). Any model error, timeout or schema
violation falls back to the deterministic planner automatically (`planner_source` shows `llm`
or `llm_fallback`). OpenAI no longer offers free API credits; **Groq** (free, no card) is
recommended. The deterministic parser is used by default (one model call per run); set
`FIXPOINT_LLM_PARSE_ENABLED=true` to also extract facts with the model.

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
| `POST` | `/api/webhooks/stripe` | Stripe-signed events: verify, dedupe, record, link to run, flag mismatches |
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
| `FIXPOINT_STRIPE_BACKEND` | empty | `twin`, `arga` or `stripe`; empty follows `FIXPOINT_PROVIDER_BACKEND` |
| `FIXPOINT_STRIPE_API_KEY` | empty | Stripe **test** key (`sk_test_...`); live keys require acknowledgement |
| `FIXPOINT_STRIPE_WEBHOOK_SECRET` | empty | Signing secret for `POST /api/webhooks/stripe` |
| `FIXPOINT_STRIPE_API_VERSION` | `2024-06-20` | Pinned `Stripe-Version` header sent to Stripe |
| `FIXPOINT_STRIPE_TIMEOUT_SECONDS` | `10` | Stripe HTTP timeout (connect capped at 3s) |
| `FIXPOINT_STRIPE_MAX_RETRIES` | `2` | GET retries on 408/429/5xx; refund POSTs are never retried client-side |
| `FIXPOINT_STRIPE_ALLOW_LIVE` | `false` | Required before an `sk_live_...` key is accepted |
| `FIXPOINT_CRM_BACKEND` | empty | `twin`, `arga` or `hubspot`; empty follows `FIXPOINT_PROVIDER_BACKEND` |
| `FIXPOINT_HUBSPOT_TOKEN` | empty | Private-app token (`pat-...`); writes to a real portal — never commit |
| `FIXPOINT_HUBSPOT_STATUS_PROPERTY` | `fixpoint_status` | Contact property read/written for CRM status |
| `FIXPOINT_HUBSPOT_REFUND_STATUS` | empty | If set, status written to the contact after a successful refund |
| `FIXPOINT_HUBSPOT_TIMEOUT_SECONDS` | `10` | HubSpot HTTP timeout |
| `FIXPOINT_HUBSPOT_MAX_RETRIES` | `2` | Read retries on 429/5xx; writes retry on 429 only |
| `FIXPOINT_HUBSPOT_WEBHOOK_SECRET` | empty | Reserved for future public-app intake (unused in v1) |
| `FIXPOINT_NOTIFY_FORMSPREE_ENABLED` | `false` | Email a Formspree inbox when a refund is approved or denied (agent or human) |
| `FIXPOINT_NOTIFY_FORMSPREE_FORM_ID` | empty | Formspree form id (e.g. `xaeygdwn`) used for decision emails |
| `FIXPOINT_NOTIFY_FORMSPREE_TIMEOUT_SECONDS` | `5` | Delivery timeout before the notification is dropped |
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
