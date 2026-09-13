# Fixpoint — Two-Minute Demo Script

Total: **120 seconds**. The value proposition must land in the first 15 seconds.

## Pre-flight (do before judging)

- Open the deployed console on the **Run Console** tab, plus a second tab on **Evaluation**.
- Confirm `/health` is green and one warm-up run has completed (so the first click is fast).
- Have the **Injection $2,000** and **Inject Stripe 500** controls visible without scrolling.
- Fallback ready: a recorded screen capture of the exact same sequence.

---

## 0:00–0:15 — Problem

**Say:** "One refund takes a support agent 20 minutes across five apps: the inbox, Stripe,
the CRM, Slack, and a policy doc. Humans are the glue — and mistakes move real money."

**Show:** the run console, or a quick split of the five apps.

## 0:15–0:25 — The request

**Type** (or click the **Double charge** preset):

> "I was double charged, please refund the duplicate charge for jane@acme.com"

Set amount to **$42** (the `$42 (team lead approval)` preset).

## 0:25–1:15 — The agent executes across apps

**Say:** "One request. The agent reads the email as untrusted data, resolves the customer,
pulls the Stripe charges, reads the refund policy from Drive — and now it wants to move
money, so it stops."

**Show:**
- The **timeline** filling in: plan → proposal → gateway decision **REQUIRE_APPROVAL**.
- The **approval panel**: source-of-truth facts (customer, both charges, policy hash), the
  **exact sealed action + action hash**, and the AI justification clearly labelled
  **UNTRUSTED**.
- **Click Approve** (role `team_lead`).
- The timeline continues: approval → mutation → CRM note → Slack audit → **Gmail draft
  (never sent)** → **verification** → report.
- Point at **System state**: one charge now shows `refunded_cents = 4200`.

**Say:** "It refunded exactly once, synced every system, and left an unsent draft for human
review. The verifier re-read the state and the audit hash chain is intact."

## 1:15–1:40 — Recovery and refusal

**Recovery:** tick **Inject Stripe 500 on refund**, run again at a small ($20) amount.
**Say:** "The payment API just failed. The agent detected it and retried with the *same*
idempotency key — so exactly one refund exists, not two."

**Refusal:** click the **Injection $2,000** preset and run.
**Say:** "Now an attacker embeds an instruction: refund $2,000 to a new card. The gateway
refuses it — over the envelope, destination not pinned — logs it as an **unsafe-blocked**
event, and escalates. Zero dollars moved."

## 1:40–1:55 — Proof

Switch to the **Evaluation** tab and click **Run full matrix**.

**Say:** "This is how we know it works. Sixteen security and reliability scenarios:
**16 of 16 pass, zero unsafe mutations.**" Then press **Tamper** on an audit chain: "and any
tampering with the record is detected instantly."

Show the **Planner** field on a run: `deterministic` (or `llm`) `/ twin` — the model proposes,
deterministic code authorizes.

## 1:55–2:00 — Punchline

**Say:** "Fixpoint doesn't just do the work. It proves it — every time."

---

## Beat sheet (quick reference)

| Time | Beat | Action |
| --- | --- | --- |
| 0:00–0:15 | Problem | 5 apps, 20 minutes, human glue |
| 0:15–0:25 | Request | Double-charge preset, $42 |
| 0:25–1:15 | Execute | timeline → approval panel → **Approve** → sync → verify |
| 1:15–1:40 | Recover + refuse | Stripe 500 retry; Injection $2,000 blocked |
| 1:40–1:55 | Reliability | 16/16 PASS, 0 unsafe, tamper detection |
| 1:55–2:00 | Punchline | "It proves it — every time." |

## If the live demo fails

1. **Network/LLM issue:** the app falls back to the deterministic planner automatically;
   say so and continue — nothing changes in the console.
2. **Provider issue:** the in-process twins are local and deterministic; only the
   `arga` backend depends on an external sandbox.
3. **Total failure:** play the recorded fallback capture and narrate the same beats.
