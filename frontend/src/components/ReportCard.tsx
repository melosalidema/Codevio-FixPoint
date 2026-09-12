import type { RunReport, Verification } from "../api/types";
import { StatusPill } from "./Pills";

export function ReportCard({
  report,
  verification,
}: {
  report: RunReport | null;
  verification: Verification | null;
}) {
  if (!report) {
    return <p className="py-4 text-center text-sm text-slate-500">No verifier report yet.</p>;
  }

  const checks = verification?.checks ?? [];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Status", value: <StatusPill status={report.status} /> },
          { label: "Outcome", value: <span className="text-sm font-medium">{report.outcome}</span> },
          {
            label: "Verified",
            value: <StatusPill status={report.verified ? "verified" : "failed"} />,
          },
          { label: "Unsafe blocked", value: <span className="text-sm font-medium">{report.unsafe_blocked}</span> },
        ].map((item) => (
          <div key={item.label} className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
            <div className="text-xs uppercase tracking-wider text-slate-500">{item.label}</div>
            <div className="mt-1">{item.value}</div>
          </div>
        ))}
      </div>

      <p className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-sm text-slate-300">
        {report.report_text}
      </p>

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-emerald-300">
            Grounded claims ({report.grounded_claims.length})
          </h3>
          <ul className="space-y-1 text-sm">
            {report.grounded_claims.map((claim) => (
              <li key={claim} className="flex items-start gap-2 text-slate-300">
                <span aria-hidden="true" className="mt-0.5 text-emerald-400">
                  ✓
                </span>
                {claim}
              </li>
            ))}
            {report.grounded_claims.length === 0 && <li className="text-slate-500">None</li>}
          </ul>
        </div>
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-rose-300">
            Ungrounded claims ({report.ungrounded_claims.length})
          </h3>
          <ul className="space-y-1 text-sm">
            {report.ungrounded_claims.map((claim) => (
              <li key={claim} className="flex items-start gap-2 text-slate-300">
                <span aria-hidden="true" className="mt-0.5 text-rose-400">
                  ✕
                </span>
                {claim}
              </li>
            ))}
            {report.ungrounded_claims.length === 0 && <li className="text-slate-500">None</li>}
          </ul>
        </div>
      </div>

      {checks.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Independent checks
          </h3>
          <div className="flex flex-wrap gap-2">
            {checks.map((check) => (
              <span
                key={check.name}
                title={check.detail}
                className={
                  check.passed
                    ? "inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-300"
                    : "inline-flex items-center gap-1 rounded-full border border-rose-500/40 bg-rose-500/10 px-2.5 py-0.5 text-xs font-medium text-rose-300"
                }
              >
                {check.passed ? "✓" : "✕"} {check.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
