import type { WorldSnapshot } from "../api/types";
import { usd } from "../lib/format";

export function StateDiff({
  before,
  after,
}: {
  before: WorldSnapshot | null;
  after: WorldSnapshot | null;
}) {
  if (!after) {
    return <p className="py-4 text-center text-sm text-slate-500">No system state available yet.</p>;
  }
  const b = before ?? { charges: {}, contacts: {}, drafts: [], slack: [] };
  const chargeIds = Array.from(new Set([...Object.keys(b.charges ?? {}), ...Object.keys(after.charges ?? {})]));

  const contactValues = Object.values(after.contacts ?? {});
  const notesTotal = contactValues.reduce((total, contact) => total + (contact.notes ?? 0), 0);
  const drafts = after.drafts ?? [];
  const slack = after.slack ?? [];

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Billing (Stripe) — refunded cents
        </h3>
        <div className="space-y-1.5">
          {chargeIds.length === 0 && <p className="text-sm text-slate-500">No charges.</p>}
          {chargeIds.map((chargeId) => {
            const beforeCharge = b.charges?.[chargeId];
            const afterCharge = after.charges?.[chargeId];
            const from = beforeCharge?.refunded_cents ?? 0;
            const to = afterCharge?.refunded_cents ?? 0;
            const changed = from !== to;
            return (
              <div
                key={chargeId}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm"
              >
                <code className="font-mono text-xs text-slate-300">{chargeId}</code>
                <span className={changed ? "font-semibold text-emerald-300" : "text-slate-400"}>
                  {usd(from)} → {usd(to)} ({afterCharge?.status ?? "-"})
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Sync across apps</h3>
        <div className="space-y-1.5">
          <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm">
            <span>CRM notes</span>
            <span className="font-semibold text-sky-300">{notesTotal}</span>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm">
            <span>Gmail drafts (never sent)</span>
            <span className="font-semibold text-sky-300">{drafts.length}</span>
          </div>
          {drafts.map((draft) => (
            <div
              key={draft.id}
              className="flex items-center justify-between rounded-lg border border-slate-800/60 bg-slate-950/30 px-3 py-1.5 text-xs text-slate-400"
            >
              <span>draft → {draft.to}</span>
              <span>sent={String(draft.sent)}</span>
            </div>
          ))}
          <div className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2 text-sm">
            <span>Slack audit posts</span>
            <span className="font-semibold text-sky-300">{slack.length}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
