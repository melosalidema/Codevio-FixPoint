import { useEffect, useState } from "react";

import { useDecision } from "../api/hooks";
import type { RunDetail } from "../api/types";
import { shortHash, usd } from "../lib/format";
import { StatusPill } from "./Pills";
import { Spinner } from "./Ui";
import { useToast } from "./Toasts";

const ROLES = ["team_lead", "finance", "finance_dual"] as const;

export function ApprovalPanel({
  run,
  onUpdated,
}: {
  run: RunDetail;
  onUpdated: (run: RunDetail) => void;
}) {
  const toast = useToast();
  const { approve, deny } = useDecision(run.run_id, onUpdated);
  const artifact = run.approval_artifact;
  const [role, setRole] = useState<string>(artifact?.required_role ?? "team_lead");
  const [approverId, setApproverId] = useState("u_99");

  useEffect(() => {
    if (artifact) setRole(artifact.required_role);
  }, [artifact?.run_id, artifact?.required_role]);

  if (!artifact || artifact.status !== "pending" || run.status !== "awaiting_approval") {
    return null;
  }

  const pending = approve.isPending || deny.isPending;

  const decide = (kind: "approve" | "deny") => {
    const mutation = kind === "approve" ? approve : deny;
    mutation.mutate(
      { approver_user_id: approverId.trim() || "u_99", role: role as (typeof ROLES)[number] },
      {
        onSuccess: (updated) => {
          toast.push(
            kind === "approve" ? "success" : "info",
            kind === "approve"
              ? `Approved and re-verified (status: ${updated.status}).`
              : "Denied — no money moved and records were reconciled.",
          );
        },
        onError: (error) => toast.push("error", error.message),
      },
    );
  };

  const customers = artifact.facts.customers ?? [];
  const charges = artifact.facts.charges ?? [];

  return (
    <section className="panel border-amber-500/50" aria-label="Human approval required">
      <div className="panel-head border-amber-500/30">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-amber-200">Human approval required</h2>
          <StatusPill status={artifact.required_role} />
        </div>
        <span className="text-sm font-semibold text-amber-200">{usd(artifact.amount_cents)}</span>
      </div>

      <div className="grid gap-5 p-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Facts (from source-of-truth APIs)
          </h3>
          {customers.length > 0 && (
            <div className="mb-3 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr>
                    <th className="py-1 pr-3">Customer</th>
                    <th className="py-1 pr-3">Email</th>
                    <th className="py-1">Id</th>
                  </tr>
                </thead>
                <tbody>
                  {customers.map((customer) => (
                    <tr key={customer.id} className="border-t border-slate-800">
                      <td className="py-1.5 pr-3">{customer.name}</td>
                      <td className="py-1.5 pr-3">{customer.email}</td>
                      <td className="py-1.5 font-mono text-xs text-slate-400">{customer.id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {charges.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr>
                    <th className="py-1 pr-3">Charge</th>
                    <th className="py-1 pr-3">Amount</th>
                    <th className="py-1 pr-3">Status</th>
                    <th className="py-1">Refunded</th>
                  </tr>
                </thead>
                <tbody>
                  {charges.map((charge) => (
                    <tr key={charge.id} className="border-t border-slate-800">
                      <td className="py-1.5 pr-3 font-mono text-xs">{charge.id}</td>
                      <td className="py-1.5 pr-3">{usd(charge.amount_cents)}</td>
                      <td className="py-1.5 pr-3">{charge.status}</td>
                      <td className="py-1.5">{usd(charge.refunded_cents)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {artifact.facts.policy_hash ? (
            <p className="mt-3 text-xs text-slate-500">
              Policy: <code className="code">{artifact.facts.policy_hash}</code>
            </p>
          ) : null}
        </div>

        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Exact sealed action</h3>
          <pre className="max-h-56 overflow-auto rounded-lg border border-slate-800 bg-slate-950/80 p-3 font-mono text-xs text-indigo-100">
            {JSON.stringify(artifact.action, null, 2)}
            {"\n\naction_hash: "}
            {shortHash(artifact.action_hash, 32)}
          </pre>
          <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wider text-slate-400">
            AI justification <span className="ml-1 rounded bg-rose-500/20 px-1.5 py-0.5 text-rose-300">UNTRUSTED</span>
          </h3>
          <p className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-sm text-slate-300">
            {artifact.untrusted_justification || "(none)"}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3 border-t border-amber-500/20 px-4 py-3">
        <label className="text-sm">
          <span className="mb-1 block text-xs text-slate-400">Approver role</span>
          <select value={role} onChange={(event) => setRole(event.target.value)} className="input w-44">
            {ROLES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-slate-400">Approver id</span>
          <input
            value={approverId}
            onChange={(event) => setApproverId(event.target.value)}
            className="input w-40"
          />
        </label>
        <div className="flex gap-2 pb-0.5">
          <button type="button" className="btn-success" disabled={pending} onClick={() => decide("approve")}>
            {approve.isPending ? <Spinner /> : null} Approve
          </button>
          <button type="button" className="btn-danger" disabled={pending} onClick={() => decide("deny")}>
            {deny.isPending ? <Spinner /> : null} Deny
          </button>
        </div>
        <p className="w-full text-xs text-slate-500">
          The approval binds to one action hash. Any change after approval voids the token (scenario S16).
        </p>
      </div>
    </section>
  );
}
