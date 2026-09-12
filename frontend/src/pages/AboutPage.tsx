import { useConfig } from "../api/hooks";
import { Panel } from "../components/Ui";
import { usd } from "../lib/format";

const PIPELINE = [
  ["1. Untrusted content", "Email, CRM notes, Slack and Drive are treated strictly as data. Instructions inside are flagged, never executed."],
  ["2. Quarantine parser", "Converts text into strict structured facts. Tools disabled — an injection here cannot act."],
  ["3. Planner", "Proposes one action at a time. It has no execution authority; it can only propose."],
  ["4. Sealed RunContext", "Tenant, actor, capabilities and envelope are injected server-side and cannot be named by the model."],
  ["5. Action Gateway", "Deny-by-default policy enforcement. Tool allow-list, tenant binding, field allow-list, destination pinning, idempotency, velocity, amount tiers."],
  ["6. Human approval", "Over-envelope or flagged actions pause for a bound, single-use, HMAC-signed approval token."],
  ["7. Adapters", "Tenant-scoped clients. Gmail is draft-only, Slack is channel-allow-listed, Drive is read-only."],
  ["8. Verifier", "Re-reads provider state: required outcome, forbidden side effects, cross-system sync, claim grounding."],
  ["9. Audit chain", "Append-only, hash-chained ledger. Any tampering is detectable at the exact entry."],
];

export function AboutPage() {
  const config = useConfig();
  const envelope = config.data?.envelope;

  const tiers = envelope
    ? [
        { range: `≤ ${usd(envelope.auto_approve_cents)}`, behavior: "Autonomous" },
        { range: `≤ ${usd(envelope.team_lead_cents)}`, behavior: "Team-lead approval" },
        { range: `≤ ${usd(envelope.dual_approval_cents)}`, behavior: "Finance approval" },
        { range: `> ${usd(envelope.dual_approval_cents)} or over cap`, behavior: "Dual approval + separation of duties" },
      ]
    : [];

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <Panel title="How Fixpoint works">
        <p className="mb-4 text-sm text-slate-300">
          Fixpoint is a multi-app agent that resolves customer exceptions and <em>proves</em> it. The model proposes;
          deterministic code authorizes; a human approves money; an independent verifier re-reads real state before
          the agent is allowed to claim success.
        </p>
        <ol className="space-y-3">
          {PIPELINE.map(([title, description]) => (
            <li key={title} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
              <div className="text-sm font-semibold text-white">{title}</div>
              <div className="mt-1 text-sm text-slate-400">{description}</div>
            </li>
          ))}
        </ol>
      </Panel>

      <div className="space-y-6">
        <Panel title="Approval envelope">
          {envelope ? (
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="py-1 pr-3">Amount</th>
                  <th className="py-1">Behavior</th>
                </tr>
              </thead>
              <tbody>
                {tiers.map((tier) => (
                  <tr key={tier.range} className="border-t border-slate-800">
                    <td className="py-2 pr-3 font-mono text-xs">{tier.range}</td>
                    <td className="py-2">{tier.behavior}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-slate-500">Loading envelope…</p>
          )}
          <p className="mt-3 text-xs text-slate-500">
            Envelope values are configuration, sealed server-side in the RunContext. The model can never edit them.
          </p>
        </Panel>

        <Panel title="Try it">
          <ul className="space-y-2 text-sm text-slate-300">
            <li>
              Run the <span className="text-white">Injection $2,000</span> preset: refused and logged as unsafe-blocked.
            </li>
            <li>
              Run a <span className="text-white">$42</span> duplicate refund: paused for team-lead approval, then
              executed once and verified.
            </li>
            <li>
              Tick <span className="text-white">Inject Stripe 500</span>: the retry is idempotent, so only one refund
              exists.
            </li>
            <li>
              Open <span className="text-white">Evaluation</span>: 16 security scenarios, PASS/FAIL and unsafe-blocked
              scoreboard.
            </li>
            <li>
              Press <span className="text-white">Tamper</span> on the audit chain: the hash chain detects it instantly.
            </li>
          </ul>
        </Panel>

        <Panel title="Links">
          <div className="flex flex-wrap gap-3 text-sm">
            <a className="btn-ghost" href="/docs" target="_blank" rel="noopener noreferrer">
              OpenAPI docs
            </a>
            <a className="btn-ghost" href="/health" target="_blank" rel="noopener noreferrer">
              Health probe
            </a>
          </div>
        </Panel>
      </div>
    </div>
  );
}
