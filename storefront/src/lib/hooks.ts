import { useQuery } from "@tanstack/react-query";

import { fixpoint } from "./fixpoint";

/** Live control-plane config: connection status + the sealed refund envelope. */
export function useFixpointConfig() {
  return useQuery({
    queryKey: ["fixpoint", "config"],
    queryFn: fixpoint.config,
    retry: false,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
}

/** One Fixpoint run, auto-polling while it waits for a human decision. */
export function useRun(runId: string | undefined) {
  return useQuery({
    queryKey: ["fixpoint", "run", runId],
    queryFn: () => fixpoint.getRun(runId as string),
    enabled: Boolean(runId),
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === "awaiting_approval" ? 4_000 : false),
  });
}
