# Fixpoint — Deploy & LLM Activation Runbook

Three independent things: (1) turn on the LLM planner, (2) deploy to Railway, (3) use Postgres.

---

## 1. Enable the LLM planner

The LLM parser/planner is already implemented and env-gated. It only *proposes*; the
deterministic Action Gateway still authorizes, and **any** LLM error/timeout/schema
violation falls back to the deterministic planner (visible as `planner_source`).

Set these (shell, or a gitignored `backend/.env`):

| Variable | Example | Notes |
| --- | --- | --- |
| `FIXPOINT_LLM_ENABLED` | `true` | must be `true` |
| `FIXPOINT_LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `FIXPOINT_LLM_API_KEY` | `sk-...` | required, non-empty |
| `FIXPOINT_LLM_MODEL` | `gpt-4o-mini` | model id |
| `FIXPOINT_LLM_TIMEOUT_SECONDS` | `20` | fallback after this |

Provider examples:

| Provider | Base URL | Key |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | `sk-...` |
| LM Studio (local) | `http://localhost:1234/v1` | any (e.g. `lm-studio`) |
| Ollama (local) | `http://localhost:11434/v1` | `ollama` |
| OpenRouter / Together / vLLM | their `/v1` | their key |

### Demo/CI without a model (mock)

```bash
cd backend
python -m scripts.mock_llm_server --port 8123
# in another shell:
FIXPOINT_LLM_ENABLED=true FIXPOINT_LLM_BASE_URL=http://localhost:8123/v1 \
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
