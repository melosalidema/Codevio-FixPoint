import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useRun } from "../api/hooks";
import type { RunDetail } from "../api/types";
import { RunDetailView } from "../components/RunDetailView";
import { EmptyState, Panel, Spinner } from "../components/Ui";

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const query = useRun(runId);
  const [override, setOverride] = useState<RunDetail | null>(null);
  const run = override ?? query.data;

  if (query.isLoading) {
    return (
      <Panel>
        <EmptyState>
          <span className="inline-flex items-center gap-2">
            <Spinner /> Loading run…
          </span>
        </EmptyState>
      </Panel>
    );
  }

  if (query.isError || !run) {
    return (
      <Panel>
        <EmptyState>
          Run not found.{" "}
          <Link to="/runs" className="text-indigo-300 underline-offset-2 hover:underline">
            Back to history
          </Link>
        </EmptyState>
      </Panel>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm">
        <Link to="/runs" className="text-indigo-300 underline-offset-2 hover:underline">
          ← Run history
        </Link>
        <span className="font-mono text-xs text-slate-500">{run.run_id}</span>
      </div>
      <RunDetailView run={run} onUpdated={setOverride} />
    </div>
  );
}
