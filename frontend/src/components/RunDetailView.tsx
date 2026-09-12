import type { RunDetail } from "../api/types";
import { when } from "../lib/format";
import { ApprovalPanel } from "./ApprovalPanel";
import { AuditChain } from "./AuditChain";
import { StatusPill } from "./Pills";
import { ReportCard } from "./ReportCard";
import { StateDiff } from "./StateDiff";
import { Timeline } from "./Timeline";
import { EmptyState, Panel } from "./Ui";

function SummaryGrid({ run }: { run: RunDetail }) {
  const items = [
    { label: "Run", value: <code className="code">{run.run_id.slice(0, 10)}</code> },
    { label: "Tenant", value: <code className="code">{run.tenant_id}</code> },
    { label: "Status", value: <StatusPill status={run.status} /> },
    { label: "Outcome", value: <span className="text-sm">{run.outcome || "-"}</span> },
    { label: "Verified", value: <StatusPill status={run.verified ? "verified" : "failed"} /> },
    { label: "Created", value: <span className="text-xs text-slate-400">{when(run.created_at)}</span> },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {items.map((item) => (
        <div key={item.label} className="rounded-lg border border-slate-800 bg-slate-950/50 px-3 py-2">
          <div className="text-xs uppercase tracking-wider text-slate-500">{item.label}</div>
          <div className="mt-1">{item.value}</div>
        </div>
      ))}
    </div>
  );
}

export function RunDetailView({
  run,
  onUpdated,
  animateTimeline = false,
}: {
  run: RunDetail;
  onUpdated: (run: RunDetail) => void;
  animateTimeline?: boolean;
}) {
  return (
    <div className="space-y-6">
      <ApprovalPanel run={run} onUpdated={onUpdated} />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <Panel
          title="Run timeline"
          actions={<StatusPill status={run.status} />}
          className="min-h-[300px]"
        >
          <Timeline entries={run.audit.entries} animate={animateTimeline} />
        </Panel>

        <div className="space-y-6">
          <Panel title="Run summary">
            <SummaryGrid run={run} />
          </Panel>
          <Panel title="Verifier report">
            <ReportCard report={run.report} verification={run.verification} />
          </Panel>
          <Panel title="Audit chain">
            <AuditChain run={run} />
          </Panel>
        </div>
      </div>

      <Panel title="System state" actions={<span className="text-xs text-slate-500">before → after</span>}>
        <StateDiff before={run.world_before} after={run.world_after} />
      </Panel>

      {!run.report && (
        <Panel title="Report">
          <EmptyState>No report yet.</EmptyState>
        </Panel>
      )}
    </div>
  );
}
