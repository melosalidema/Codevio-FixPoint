import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./client";
import type { DecisionRequest, RunCreateRequest, RunDetail } from "./types";

export const queryKeys = {
  config: ["config"] as const,
  runs: ["runs"] as const,
  run: (runId: string) => ["run", runId] as const,
  scenarios: ["scenarios"] as const,
  evalResults: ["eval-results"] as const,
};

export function useConfig() {
  return useQuery({ queryKey: queryKeys.config, queryFn: api.config, staleTime: 60_000 });
}

export function useRuns() {
  return useQuery({ queryKey: queryKeys.runs, queryFn: api.listRuns });
}

export function useRun(runId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.run(runId ?? ""),
    queryFn: () => api.getRun(runId as string),
    enabled: Boolean(runId),
  });
}

export function useCreateRun(onSuccess: (run: RunDetail) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RunCreateRequest) => api.createRun(body),
    onSuccess: (run) => {
      queryClient.setQueryData(queryKeys.run(run.run_id), run);
      queryClient.invalidateQueries({ queryKey: queryKeys.runs });
      onSuccess(run);
    },
  });
}

export function useDecision(runId: string, onSuccess: (run: RunDetail) => void) {
  const queryClient = useQueryClient();
  const update = (run: RunDetail) => {
    queryClient.setQueryData(queryKeys.run(run.run_id), run);
    queryClient.setQueryData(queryKeys.run(runId), run);
    queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    onSuccess(run);
  };
  const approve = useMutation({
    mutationFn: (body: DecisionRequest) => api.approve(runId, body),
    onSuccess: update,
  });
  const deny = useMutation({
    mutationFn: (body: DecisionRequest) => api.deny(runId, body),
    onSuccess: update,
  });
  return { approve, deny };
}

export function useScenarios() {
  return useQuery({ queryKey: queryKeys.scenarios, queryFn: api.scenarios });
}

export function useRunScenario() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (scenarioId: string) => api.runScenario(scenarioId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.evalResults }),
  });
}

export function useRunEvals(onSuccess?: (batchId: string) => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.runEvals,
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.evalResults, {
        batch_id: data.batch_id,
        total: data.total,
        passed: data.passed,
        unsafe_blocked: data.unsafe_blocked,
        results: data.results,
      });
      onSuccess?.(data.batch_id);
    },
  });
}

export function useEvalResults() {
  return useQuery({ queryKey: queryKeys.evalResults, queryFn: api.evalResults });
}

export function useTamper(onUpdated: (audit: RunDetail["audit"]) => void) {
  return useMutation({
    mutationFn: (runId: string) => api.tamper(runId),
    onSuccess: onUpdated,
  });
}
