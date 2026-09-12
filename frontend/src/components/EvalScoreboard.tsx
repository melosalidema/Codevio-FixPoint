import type { EvalResults, ScenarioResult } from "../api/types";
import { cn } from "../lib/cn";
import { EmptyState, Spinner } from "./Ui";

interface EvalScoreboardProps {
  results: EvalResults | undefined;
  running: boolean;
  runningScenarioId: string | null;
  onRunAll: () => void;
  onRunOne: (scenarioId: string) => void;
  resultsById: Record<string, ScenarioResult>;
}

export function EvalScoreboard({
  results,
  running,
  runningScenarioId,
  onRunAll,
  onRunOne,
  resultsById,
}: EvalScoreboardProps) {
  const total = results?.total ?? 0;
  const passed = results?.passed ?? 0;
  const failed = Math.max(0, total - passed);
  const blocked = results?.unsafe_blocked ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-white">S1–S16 security &amp; reliability matrix</h2>
          <p className="text-sm text-slate-400">
            Each scenario runs against freshly seeded providers. PASS means the expected safe outcome held.
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={onRunAll} disabled={running}>
          {running ? <Spinner /> : null} {running ? "Running matrix…" : "Run full matrix"}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {[
          { label: "PASS", value: passed, className: "border-emerald-500/40 text-emerald-300" },
          { label: "FAIL", value: failed, className: "border-rose-500/40 text-rose-300" },
          { label: "unsafe blocked", value: blocked, className: "border-amber-500/40 text-amber-300" },
        ].map((card) => (
          <div key={card.label} className={cn("rounded-xl border bg-slate-900/60 px-4 py-3 text-center", card.className)}>
            <div className="text-2xl font-bold">{card.value}</div>
            <div className="text-xs uppercase tracking-wider text-slate-400">{card.label}</div>
          </div>
        ))}
      </div>

      <p className="text-sm text-slate-400">
        {total === 0
          ? "No results yet — run the matrix or a single scenario."
          : passed === total
            ? `All ${total} scenarios held their safe outcome. ${blocked} unsafe action(s) were blocked by the gateway.`
            : `${failed} scenario(s) failed — review the table below.`}
      </p>

      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400">
            <tr>
              <th className="px-3 py-2">ID</th>
              <th className="px-3 py-2">Scenario</th>
              <th className="px-3 py-2">Result</th>
              <th className="px-3 py-2">Observed</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {results?.results?.length ? (
              results.results.map((result) => (
                <ScenarioRow
                  key={result.id}
                  result={resultsById[result.id] ?? result}
                  running={runningScenarioId === result.id}
                  onRun={() => onRunOne(result.id)}
                />
              ))
            ) : (
              <tr>
                <td colSpan={5}>
                  <EmptyState>Run the matrix to populate results.</EmptyState>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ScenarioRow({
  result,
  running,
  onRun,
}: {
  result: ScenarioResult;
  running: boolean;
  onRun: () => void;
}) {
  return (
    <tr className="border-t border-slate-800 odd:bg-slate-900/30">
      <td className="px-3 py-2 font-mono text-xs text-slate-300">{result.id}</td>
      <td className="px-3 py-2">{result.title}</td>
      <td className="px-3 py-2">
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-xs font-semibold",
            result.passed
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "border-rose-500/40 bg-rose-500/10 text-rose-300",
          )}
        >
          {result.passed ? "PASS" : "FAIL"}
        </span>
      </td>
      <td className="max-w-[280px] truncate px-3 py-2 font-mono text-xs text-slate-400" title={JSON.stringify(result.observed)}>
        {JSON.stringify(result.observed)}
      </td>
      <td className="px-3 py-2 text-right">
        <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={onRun} disabled={running}>
          {running ? <Spinner /> : null} run
        </button>
      </td>
    </tr>
  );
}
