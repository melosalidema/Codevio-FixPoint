import { Link } from "react-router-dom";

import { useRuns } from "../api/hooks";
import { StatusPill } from "../components/Pills";
import { EmptyState, Panel, Spinner } from "../components/Ui";
import { shortHash, when } from "../lib/format";

export function RunsPage() {
  const runs = useRuns();

  return (
    <Panel
      title="Run history"
      actions={
        <button type="button" className="btn-ghost text-xs" onClick={() => runs.refetch()} disabled={runs.isFetching}>
          {runs.isFetching ? <Spinner /> : null} Refresh
        </button>
      }
    >
      {runs.isError ? (
        <EmptyState>Could not load runs: {runs.error.message}</EmptyState>
      ) : runs.isLoading ? (
        <EmptyState>Loading runs…</EmptyState>
      ) : !runs.data?.length ? (
        <EmptyState>No runs yet. Start one from the Run Console.</EmptyState>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-slate-400">
              <tr>
                <th className="px-3 py-2">Run</th>
                <th className="px-3 py-2">Request</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Verified</th>
                <th className="px-3 py-2">Unsafe blocked</th>
                <th className="px-3 py-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((run) => (
                <tr key={run.run_id} className="border-t border-slate-800 odd:bg-slate-900/30">
                  <td className="px-3 py-2">
                    <Link
                      to={`/runs/${run.run_id}`}
                      className="font-mono text-xs text-indigo-300 underline-offset-2 hover:underline"
                    >
                      {shortHash(run.run_id, 10)}
                    </Link>
                  </td>
                  <td className="max-w-[320px] truncate px-3 py-2 text-slate-300" title={run.request_text}>
                    {run.request_text}
                  </td>
                  <td className="px-3 py-2">
                    <StatusPill status={run.status} />
                  </td>
                  <td className="px-3 py-2">
                    <StatusPill status={run.verified ? "verified" : "failed"} />
                  </td>
                  <td className="px-3 py-2">{run.unsafe_blocked}</td>
                  <td className="px-3 py-2 text-xs text-slate-400">{when(run.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
