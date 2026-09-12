import { useEffect, useState } from "react";

import { useConfig, useTamper } from "../api/hooks";
import type { AuditResponse, RunDetail } from "../api/types";
import { shortHash, titleCase } from "../lib/format";
import { Pill } from "./Pills";
import { useToast } from "./Toasts";
import { Spinner } from "./Ui";

export function AuditChain({ run }: { run: RunDetail }) {
  const config = useConfig();
  const toast = useToast();
  const [audit, setAudit] = useState<AuditResponse>(run.audit);

  useEffect(() => {
    setAudit(run.audit);
  }, [run.audit]);

  const tamper = useTamper((updated) => {
    setAudit(updated);
    toast.push("error", `Tamper detected: ${updated.reason}`);
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Pill tone={audit.chain_ok ? "ok" : "crit"}>
          {audit.chain_ok ? `chain intact (${audit.entries.length})` : `CHAIN BROKEN — ${audit.reason}`}
        </Pill>
        {config.data?.demo_mode ? (
          <button
            type="button"
            className="btn-ghost text-xs"
            disabled={tamper.isPending}
            onClick={() =>
              tamper.mutate(run.run_id, {
                onError: (error) => toast.push("error", error.message),
              })
            }
          >
            {tamper.isPending ? <Spinner /> : null} Tamper (demo)
          </button>
        ) : null}
      </div>

      <div className="max-h-72 space-y-1 overflow-auto rounded-lg border border-slate-800 bg-slate-950/60 p-2">
        {audit.entries.map((entry) => (
          <div
            key={entry.seq}
            className="flex items-center gap-3 rounded px-2 py-1 font-mono text-xs odd:bg-slate-900/40"
          >
            <span className="w-8 text-right text-slate-500">{entry.seq}</span>
            <span className="w-40 truncate text-slate-300">{titleCase(entry.type)}</span>
            <span className="truncate text-indigo-300/80">{shortHash(entry.hash)}</span>
          </div>
        ))}
        {audit.entries.length === 0 && <p className="p-2 text-slate-500">No entries.</p>}
      </div>

      <p className="text-xs text-slate-500">
        Each entry hashes the previous one. Mutating any payload makes verification fail immediately.
      </p>
    </div>
  );
}
