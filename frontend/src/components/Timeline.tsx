import type { ReactNode } from "react";

import { DecisionPill, Pill } from "./Pills";
import { EmptyState } from "./Ui";
import { cn } from "../lib/cn";
import { prettyJson, titleCase, usd } from "../lib/format";
import type { AuditEntry } from "../api/types";

// Left border color per ledger entry type.
const TYPE_BORDER: Record<string, string> = {
  plan: "border-l-sky-500/70",
  proposal: "border-l-indigo-500/70",
  gateway_decision: "border-l-violet-500/70",
  approval: "border-l-amber-500/70",
  tool_call: "border-l-slate-500/70",
  mutation: "border-l-emerald-500/70",
  verification: "border-l-teal-500/70",
  unsafe_blocked: "border-l-rose-500/70",
  report: "border-l-indigo-400/70",
};

type Payload = Record<string, any>; // rendered defensively from server payloads

function Code({ children }: { children: ReactNode }) {
  return <code className="code">{children}</code>;
}

function EntryBody({ entry }: { entry: AuditEntry }) {
  const payload = (entry.payload ?? {}) as Payload;

  switch (entry.type) {
    case "plan": {
      const facts = (payload.facts ?? {}) as Payload;
      const flags = (facts.injection_flags ?? []) as string[];
      return (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <span className="text-slate-400">
            email <Code>{facts.customer_email ?? "-"}</Code>
          </span>
          <span className="text-slate-400">
            action <Code>{facts.requested_action ?? "-"}</Code>
          </span>
          <span className="text-slate-400">
            amount <Code>{facts.amount_cents ?? "-"}</Code>
          </span>
          <span className="text-slate-400">
            customers <Code>{String(payload.customers ?? 0)}</Code>
          </span>
          <span className="text-slate-400">
            charges <Code>{String(payload.charges ?? 0)}</Code>
          </span>
          {flags.length > 0 && <Pill tone="crit">flags: {flags.join(", ")}</Pill>}
        </div>
      );
    }

    case "proposal": {
      const action = payload.action as Payload | null | undefined;
      if (!action) {
        return <span className="text-slate-400">no actionable remedy proposed</span>;
      }
      return (
        <div className="space-y-1">
          <div>
            tool <Code>{String(action.tool)}</Code> params <Code>{prettyJson(action.params, 160)}</Code>
          </div>
          {action.justification ? (
            <p className="text-xs text-slate-400">
              justification (untrusted): “{String(action.justification)}”
            </p>
          ) : null}
        </div>
      );
    }

    case "gateway_decision":
      return (
        <div className="flex flex-wrap items-center gap-2">
          <DecisionPill decision={String(payload.decision)} />
          <span className="text-slate-400">
            reason <Code>{String(payload.reason)}</Code>
          </span>
          {payload.required_role && payload.required_role !== "none" ? (
            <span className="text-slate-400">
              role <Code>{String(payload.required_role)}</Code>
            </span>
          ) : null}
        </div>
      );

    case "approval": {
      const artifact = payload.artifact as Payload | undefined;
      if (artifact) {
        return (
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="warn">{payload.escalate ? "escalated" : "approval requested"}</Pill>
            <span className="text-slate-400">
              role <Code>{String(artifact.required_role)}</Code> amount{" "}
              <Code>{usd(Number(artifact.amount_cents))}</Code>
            </span>
            {payload.reason ? <span className="text-slate-500">({String(payload.reason)})</span> : null}
          </div>
        );
      }
      const result = String(payload.result ?? "");
      return (
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={result === "approved" ? "ok" : result === "denied" ? "info" : "crit"}>{result}</Pill>
          {payload.approver ? (
            <span className="text-slate-400">
              approver <Code>{String(payload.approver)}</Code>
            </span>
          ) : null}
        </div>
      );
    }

    case "tool_call": {
      if (payload.error) {
        return (
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="crit">error</Pill>
            <Code>{String(payload.error)}</Code>
          </div>
        );
      }
      return (
        <span className="text-slate-400">
          tool <Code>{String(payload.tool ?? "unknown")}</Code>
          {payload.channel ? (
            <>
              {" "}
              channel <Code>{String(payload.channel)}</Code>
            </>
          ) : null}
          {payload.to ? (
            <>
              {" "}
              to <Code>{String(payload.to)}</Code>
            </>
          ) : null}
        </span>
      );
    }

    case "mutation": {
      const action = payload.action as Payload | undefined;
      return (
        <div className="space-y-1">
          <div>
            tool <Code>{String(action?.tool ?? "-")}</Code>
          </div>
          <div className="text-slate-400">
            result <Code>{prettyJson(payload.result, 200)}</Code>
          </div>
        </div>
      );
    }

    case "verification": {
      const checks = (payload.checks ?? []) as { name: string; passed: boolean; detail: string }[];
      return (
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={payload.passed ? "ok" : "crit"}>passed {payload.passed ? "yes" : "no"}</Pill>
          {checks.map((check) => (
            <Pill key={check.name} tone={check.passed ? "ok" : "crit"}>
              {check.name}
            </Pill>
          ))}
          {Array.isArray(payload.synced_systems) && payload.synced_systems.length > 0 ? (
            <span className="text-slate-400">
              synced <Code>{(payload.synced_systems as string[]).join(", ")}</Code>
            </span>
          ) : null}
        </div>
      );
    }

    case "unsafe_blocked":
      return (
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone="crit">REFUSED</Pill>
          <span className="text-slate-400">
            reason <Code>{String(payload.reason)}</Code>
          </span>
          {payload.action ? (
            <span className="text-slate-500">
              tool <Code>{String((payload.action as Payload).tool)}</Code>
            </span>
          ) : null}
        </div>
      );

    case "report":
      return (
        <div className="flex flex-wrap items-center gap-2">
          <span>{String(payload.report ?? "")}</span>
          <Pill tone={payload.verified ? "ok" : "crit"}>verified {payload.verified ? "yes" : "no"}</Pill>
        </div>
      );

    default:
      return <Code>{prettyJson(payload, 200)}</Code>;
  }
}

export function Timeline({ entries, animate = false }: { entries: AuditEntry[]; animate?: boolean }) {
  if (entries.length === 0) {
    return (
      <EmptyState>
        Run the agent to see each step: plan, proposal, gateway decision, approval, mutation, verification.
      </EmptyState>
    );
  }
  return (
    <ol className="space-y-2" aria-label="Run timeline">
      {entries.map((entry, index) => (
        <li
          key={entry.seq}
          className={cn(
            "animate-fade-up rounded-lg border border-l-2 border-slate-800/70 bg-slate-950/50 p-3",
            TYPE_BORDER[entry.type] ?? "border-l-slate-600",
          )}
          style={animate ? { animationDelay: `${Math.min(index, 12) * 70}ms` } : undefined}
        >
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              {titleCase(entry.type)}
            </span>
            <span className="font-mono text-xs text-slate-500">#{entry.seq}</span>
          </div>
          <div className="text-sm text-slate-200">
            <EntryBody entry={entry} />
          </div>
        </li>
      ))}
    </ol>
  );
}
