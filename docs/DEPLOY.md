# Fixpoint — Deploy & LLM Activation Runbook

Three independent things: (1) turn on the LLM planner, (2) deploy to Railway, (3) use Postgres.

---

## 1. Enable the LLM planner

The LLM parser/planner is already implemented and env-gated. It only *proposes*; the
deterministic Action Gateway still authorizes, and **any** LLM error/timeout/schema
violation falls back to the deterministic planner (visible as `planner_source`).

The quickest reliable free path is a provider key — set the provider and the key, nothing else.

| Variable | Required | Notes |
| --- | --- | --- |
| `FIXPOINT_LLM_ENABLED` | yes | `true` |
| `FIXPOINT_LLM_PROVIDER` | yes | `pollinations`, `groq`, `gemini`, `github`, `openai`, `custom` |
| `FIXPOINT_LLM_API_KEY` | for keyed providers | not needed for `pollinations` |
| `FIXPOINT_LLM_BASE_URL` / `FIXPOINT_LLM_MODEL` | `custom` only (or to override) | explicit endpoint/model |
| `FIXPOINT_LLM_TIMEOUT_SECONDS` | no | default `45` |
| `FIXPOINT_LLM_PARSE_ENABLED` | no | default `false`; keeps the deterministic parser (one model call per run) |

Built-in presets:

| Provider | Base URL | Default model | Key? | Notes |
| --- | --- | --- | --- | --- |
| `pollinations` | `https://text.pollinations.ai/openai` | `openai` | no | free/keyless, rate/budget limited |
| `groq` | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` | yes | **recommended: free, no card, fast** |
| `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.5-flash` | yes | free tier; trains on free data |
| `github` | `https://models.github.ai/inference` | `openai/gpt-4o-mini` | yes (GitHub PAT) | free; not for production |
| `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` | yes | no free tier (min $5) |
| `custom` | (you provide) | (you provide) | depends | LM Studio, Ollama, vLLM, etc. |

**Recommended free setup (Groq, no credit card):** create a key at console.groq.com, then:

```powershell
$env:FIXPOINT_LLM_ENABLED="true"
$env:FIXPOINT_LLM_PROVIDER="groq"
$env:FIXPOINT_LLM_API_KEY="gsk_..."
```

**Keyless (no signup):** `FIXPOINT_LLM_PROVIDER=pollinations` with no key — works but the
public endpoint is shared and rate/budget limited, so it may fall back to the deterministic
planner. **Local:** `provider=custom`, `base_url=http://localhost:1234/v1`, `model=<id>`.

**Note:** OpenAI discontinued free API credits in mid-2025; there is no usable free OpenAI
tier. Sites selling "free OpenAI keys" resell shared/leaked keys — do not use them. Free
tiers differ on training data (Groq: no; Gemini free: yes); Fixpoint prompts contain customer
email/charges, so prefer Groq or a local model for real data.

### Demo/CI without a model (mock)

```bash
cd backend
python -m scripts.mock_llm_server --port 8123
# in another shell:
FIXPOINT_LLM_ENABLED=true FIXPOINT_LLM_PROVIDER=custom \
FIXPOINT_LLM_BASE_URL=http://localhost:8123/v1 \
FIXPOINT_LLM_API_KEY=mock FIXPOINT_LLM_MODEL=mock-llm \
python -m uvicorn app.main:app --port 8000
```

The mock reuses Fixpoint's deterministic parser, so it is schema-valid — it proves the LLM
wiring, not model quality. Swap the base URL/key/model for a real provider for the demo.

### Verify

- `GET /api/config` → `"llm_enabled": true`, `"llm_model": "<model>"`.
- Run a `$42` duplicate charge → run detail shows `planner_source: "llm"`, still pauses for
  approval, and `audit.chain_ok` is true.
- Stop the model (or use a bad URL) and run again → `planner_source: "llm_fallback"`, the run
  still completes and verifies.
- `POST /api/evals/run` → 16/16 (evals use the deterministic planner directly).

### Safety / data notes

- The model receives only facts, charges and the policy excerpt — never tenant ids,
  capabilities, envelope values or credentials; the gateway enforces tenant binding and limits.
- Injection flags from the deterministic detector are unioned onto the LLM facts, and any
  destination named in untrusted content is force-fed to the gateway, so money can never be
  redirected even if the model omits the field.
- Prompts contain customer email/charges/policy: use a zero-retention provider or a local
  model for real data.

### Rollback

`FIXPOINT_LLM_ENABLED=false` (or unset) and restart → deterministic planner.

---

## 2. Deploy to Railway

Prereqs: repo pushed; `railway.json` builds the `Dockerfile` (Node SPA build → Python runtime)
with healthcheck `/health`.

1. railway.app → sign in with GitHub → **New Project → Deploy from GitHub repo** → pick the repo.
2. **New → Database → PostgreSQL** in the same project (see section 3).
3. On the **app service**, Settings → Variables:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
   | `FIXPOINT_SIGNING_KEY` | strong random |
   | `FIXPOINT_WEBHOOK_SECRET` | strong random |
   | `FIXPOINT_ENV` | `production` |
   | `FIXPOINT_DEMO_MODE` | `true` |
   | `FIXPOINT_LLM_*` | optional (section 1) |

   Generate secrets: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
4. Settings → Networking → **Generate Domain**.
5. Deploy. The entrypoint runs `alembic upgrade head` then binds `$PORT`.
6. Verify: `https://<domain>/health` → `database: ok`; open `/`; run + approve; Evaluation 16/16.
7. Keep **1 replica** for a deterministic demo.

`FIXPOINT_DEMO_MODE=false` disables the audit-tamper demo endpoint in anything public.

---

## 3. Postgres

No code changes are needed: `asyncpg` is a dependency, `config.py` rewrites `postgres://` and
`postgresql://` to `postgresql+asyncpg://`, and Alembic uses the same async driver.

### Railway (managed)

- Add the PostgreSQL plugin, then set the app variable `DATABASE_URL = ${{Postgres.DATABASE_URL}}`.
  **Without this the app silently uses ephemeral SQLite and loses data on redeploy.**
- Redeploy and confirm `/health` reports `database: ok`; create a run, redeploy, confirm
  `GET /api/runs` still lists it.

### Local

- Docker parity: `docker compose up --build` (Postgres 16 + API).
- Or your own Postgres:

  ```bash
  cd backend
  FIXPOINT_DATABASE_URL=postgresql://fixpoint:fixpoint@localhost:5432/fixpoint python -m alembic upgrade head
  FIXPOINT_DATABASE_URL=postgresql://fixpoint:fixpoint@localhost:5432/fixpoint python -m uvicorn app.main:app --port 8000
  ```

### Gotchas

| Gotcha | Guidance |
| --- | --- |
| `DATABASE_URL` not linked | falls back to SQLite (data lost on redeploy) |
| `postgres://` prefix | normalized automatically |
| External URL needs SSL | append `?sslmode=require` (internal URL does not) |
| Migrations | idempotent; run on every container start via `start.sh` |
| Multiple replicas | supported, but keep 1 for the demo |

---

## 4. Stripe (test mode)

Stripe is a per-service backend: it can be live while Gmail/Slack/CRM/Drive stay on twins.

### Prerequisites

- A Stripe account with **test mode** enabled (no real money).
- The [Stripe CLI](https://stripe.com/docs/stripe-cli) for local webhook forwarding.

### Configure

| Variable | Value |
| --- | --- |
| `FIXPOINT_STRIPE_BACKEND` | `stripe` |
| `FIXPOINT_STRIPE_API_KEY` | `sk_test_...` (from Developers → API keys) |
| `FIXPOINT_STRIPE_WEBHOOK_SECRET` | `whsec_...` printed by `stripe listen` |
| `FIXPOINT_STRIPE_API_VERSION` | pinned version, default `2024-06-20` |
| `FIXPOINT_STRIPE_ALLOW_LIVE` | leave `false`; required only for live keys |

A live key (`sk_live_...`) makes the app fail at startup with a clear error unless
`FIXPOINT_STRIPE_ALLOW_LIVE=true`. Never put a live key in local `.env`.

### Seed demo data

```bash
cd backend
FIXPOINT_STRIPE_API_KEY=sk_test_... python -m scripts.stripe_seed --with-subscription
```

Creates/reuses the customer `jane@acme.com`, two identical `$42` charges (PaymentIntents with
`pm_card_visa`), and an optional subscription. Re-running is safe: objects carry
`metadata.fixpoint_seed=demo` and are reused. The script refuses live keys.

### Run with webhooks

```bash
# shell 1
cd backend
FIXPOINT_STRIPE_BACKEND=stripe FIXPOINT_STRIPE_API_KEY=sk_test_... \
  FIXPOINT_STRIPE_WEBHOOK_SECRET=whsec_... \
  python -m uvicorn app.main:app --port 8000

# shell 2
stripe listen --forward-to localhost:8000/api/webhooks/stripe
```

### Demo run

Submit the suggested text from the seeder:

```text
I was double charged, please refund the duplicate charge for jane@acme.com
```

with `amount_cents=4200` (or use the storefront). The agent resolves the customer, finds the two
charges, pauses for team-lead approval (over $25), executes **one** refund with the persisted
idempotency key, verifies with fresh `GET /v1/charges/{id}` and `GET /v1/refunds?charge=` reads,
and reports `exactly_one_refund`. Stripe emits refund events, which Fixpoint verifies,
deduplicates, records, and links to the run via `metadata.run_id`; mismatches are flagged.

### Notes

- Duplicate customers for the same email trigger the existing ambiguity escalation; the agent never
  picks one.
- Client-side retries apply to GETs only. A transient refund failure is retried once by the engine
  with the same persisted key.
- `pytest -q` covers the Stripe client, webhooks and verifier with HTTP mocks; no Stripe account is
  needed for the test suite.

---

## 5. HubSpot CRM (private app)

HubSpot is an independent per-service backend; it can be live while Stripe/Gmail/Slack/Drive keep
their own configuration.

### Prerequisites

- A HubSpot developer test account or sandbox.
- A **private app** (Settings → Integrations → Private Apps) with scopes:
  `crm.objects.contacts.read`, `crm.objects.contacts.write`, `crm.objects.notes.read`,
  `crm.objects.notes.write` (add `crm.schemas.contacts.write` only if the seeder creates the
  status property). Copy the `pat-...` access token.

> HubSpot private-app tokens write to a **real portal. There is no test mode.** Use a free
> developer test account or sandbox and treat the token as a production secret.

### Configure

| Variable | Value |
| --- | --- |
| `FIXPOINT_CRM_BACKEND` | `hubspot` |
| `FIXPOINT_HUBSPOT_TOKEN` | `pat-...` (never commit) |
| `FIXPOINT_HUBSPOT_STATUS_PROPERTY` | `fixpoint_status` (default) |
| `FIXPOINT_HUBSPOT_REFUND_STATUS` | empty (no status write) or e.g. `refunded` |
| `FIXPOINT_HUBSPOT_TIMEOUT_SECONDS` | `10` |
| `FIXPOINT_HUBSPOT_MAX_RETRIES` | `2` |

A missing token with `FIXPOINT_CRM_BACKEND=hubspot` fails at startup — never a silent twin.

### Seed

```bash
cd backend
FIXPOINT_HUBSPOT_TOKEN=pat-... python -m scripts.hubspot_seed --yes
# optional:
#   --with-duplicate           second contact with the same email (ambiguity demo)
#   --create-status-property   creates fixpoint_status (needs crm.schemas.contacts.write)
```

The script warns loudly, requires `--yes` (or an interactive confirmation), is idempotent, and
never prints the token. Without `--yes` in a non-interactive shell it refuses to write.

### Demo run

```text
I was double charged, please refund the duplicate charge for jane@acme.com
```

At `amount_cents=4200` the run pauses for team-lead approval, then after approval writes a run
note associated with the pinned contact and the verifier fresh-reads that contact's notes
(`crm_note_recorded`). With `FIXPOINT_HUBSPOT_REFUND_STATUS=refunded` the status property is also
patched; when empty, no status PATCH is made. `cross_system_sync` still passes.

### Limitations

CRM-case intake is not implemented in v1: legacy private apps cannot provide the signed webhook
intake this workflow needs. Future options are a polling worker (preferred first implementation)
or a public OAuth app with `X-HubSpot-Signature-v3` verification. `FIXPOINT_HUBSPOT_WEBHOOK_SECRET`
is reserved for that work and unused in v1.
