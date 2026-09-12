import { useState } from "react";

import { useConfig, useCreateRun } from "../api/hooks";
import type { RunDetail } from "../api/types";
import { RequestForm } from "../components/RequestForm";
import { RunDetailView } from "../components/RunDetailView";
import { useToast } from "../components/Toasts";
import { EmptyState, Panel } from "../components/Ui";

export function RunConsolePage() {
  const config = useConfig();
  const toast = useToast();
  const [run, setRun] = useState<RunDetail | null>(null);

  const createRun = useCreateRun((created) => {
    setRun(created);
    if (created.status === "awaiting_approval") {
      toast.push("info", "Money action paused — human approval required.");
    } else if (created.unsafe_blocked > 0) {
      toast.push("error", "Unsafe instruction refused by the Action Gateway.");
    } else {
      toast.push("success", `Run ${created.status} and ${created.verified ? "verified" : "unverified"}.`);
    }
  });

  return (
    <div className="space-y-6">
      <Panel
        title="New request"
        actions={
          <span className="text-xs text-slate-500">
            {config.data ? `env: ${config.data.env} · v${config.data.version}` : ""}
          </span>
        }
      >
        <RequestForm
          config={config.data}
          loading={createRun.isPending}
          onSubmit={(body) =>
            createRun.mutate(body, {
              onError: (error) => toast.push("error", error.message),
            })
          }
        />
      </Panel>

      {run ? (
        <RunDetailView run={run} onUpdated={setRun} animateTimeline />
      ) : (
        <Panel title="Run timeline">
          <EmptyState>
            Submit a request above. The Step-by-step timeline, approval gate, verifier report and audit chain appear
            here.
          </EmptyState>
        </Panel>
      )}
    </div>
  );
}
