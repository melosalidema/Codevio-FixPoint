import { useState } from "react";

import { useEvalResults, useRunEvals, useRunScenario } from "../api/hooks";
import type { ScenarioResult } from "../api/types";
import { EvalScoreboard } from "../components/EvalScoreboard";
import { useToast } from "../components/Toasts";

export function EvaluationPage() {
  const toast = useToast();
  const results = useEvalResults();
  const runEvals = useRunEvals();
  const runScenario = useRunScenario();
  const [resultsById, setResultsById] = useState<Record<string, ScenarioResult>>({});

  const runAll = () => {
    runEvals.mutate(undefined, {
      onSuccess: (data) => {
        toast.push(
          data.passed === data.total ? "success" : "error",
          data.passed === data.total
            ? `${data.passed}/${data.total} PASS — zero unsafe mutations.`
            : `${data.passed}/${data.total} passed — review failing scenarios.`,
        );
      },
      onError: (error) => toast.push("error", error.message),
    });
  };

  const runOne = (scenarioId: string) => {
    runScenario.mutate(scenarioId, {
      onSuccess: (result) => {
        setResultsById((previous) => ({ ...previous, [scenarioId]: result }));
        toast.push(
          result.passed ? "success" : "error",
          `${scenarioId} ${result.passed ? "PASS" : "FAIL"}${result.failed.length ? `: ${result.failed.join(", ")}` : ""}`,
        );
      },
      onError: (error) => toast.push("error", error.message),
    });
  };

  return (
    <EvalScoreboard
      results={results.data}
      running={runEvals.isPending}
      runningScenarioId={runScenario.isPending ? (runScenario.variables ?? null) : null}
      onRunAll={runAll}
      onRunOne={runOne}
      resultsById={resultsById}
    />
  );
}
