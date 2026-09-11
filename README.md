# Fixpoint

An autonomous multi-app agent (billing, inbox, CRM, chat, docs) that resolves customer
exceptions and **proves** it. The LLM only *proposes*; deterministic code authorizes, gates
money behind a bound human approval, and an independent verifier re-reads real state before
the agent is allowed to claim success.

This repository is the concrete FastAPI/Python build of `fixpoint-plan.html`.

The original design document lives in the repo at [`docs/fixpoint-plan.html`](docs/fixpoint-plan.html)
(self-contained, no dependencies - open it in a browser or view it on GitHub Pages).

## Layout

```
core/       deterministic safety layer (the product) - no network I/O
  schemas.py      ProposedAction, RunContext, Envelope, ApprovalToken, reports
  gateway.py      Action Gateway: deny-by-default policy enforcement point
  approval.py     HMAC-signed, single-use, action-bound approval tokens
  audit.py        append-only hash-chained audit log
  canonical.py    action hashing + idempotency keys
  webhooks.py     HMAC signature + replay protection
adapters/   tenant-scoped provider clients (tenant injected from sealed context)
twins/      resettable/seedable mock providers (Arga is NOT guaranteed)
worker/     untrusted side: quarantine parser, planner, run engine, verifier
api/        FastAPI control plane
evals/      S1-S16 scenario matrix + PASS/FAIL/UNSAFE runner
tests/      deterministic unit + end-to-end tests
```

## Run it

```powershell
# unit tests (deterministic core)
python -m pytest -q

# S1-S16 security/reliability matrix
python -m evals.runner

# control plane
uvicorn api.main:app --reload
# then open http://127.0.0.1:8000/docs
```

No secrets are required. Outputs use local twins; swap `twins/` for Arga by implementing the
same methods behind `adapters/`.

## Safety model

- **Action Gateway** (`core/gateway.py`) is the only mutation path. Checks in order:
  tool allow-list, capability grant, tenant binding, forbidden ops, data guard, field
  allow-list, destination/charge pinning, velocity, idempotency, amount cap, approval tier.
- **Approval tokens** are HMAC-signed and bound to one `action_hash`, amount, tenant, nonce
  and expiry. Any post-approval change voids them (`S16`).
- **Verifier** re-reads state and asserts required outcomes, forbidden side effects and
  cross-system sync; ungrounded claims fail the run.
- **Audit log** is append-only and hash-chained; tampering is detectable (`S12`).

## Envelope (approved plan numbers)

| Amount | Behavior |
| --- | --- |
| <= $25 | autonomous |
| <= $250 | team-lead approval |
| <= $2,500 | finance approval |
| > $2,500 or over cap | dual approval + separation of duties |

## Definition of done

1. `python -m pytest -q` - all green.
2. `python -m evals.runner` - 16/16 PASS, UNSAFE = 0.
3. Two-minute demo: run, approve/deny, Stripe-500 retry, injected $2,000 blocked.
