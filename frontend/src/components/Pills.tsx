import { cn } from "../lib/cn";

export type Tone = "ok" | "warn" | "crit" | "info" | "neutral";

const TONES: Record<Tone, string> = {
  ok: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  warn: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  crit: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  neutral: "border-slate-600/50 bg-slate-700/20 text-slate-300",
};

export function Pill({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold",
        TONES[tone],
      )}
    >
      {children}
    </span>
  );
}

const STATUS_TONES: Record<string, Tone> = {
  completed: "ok",
  awaiting_approval: "warn",
  verified: "ok",
  approved: "ok",
  pending: "warn",
  denied: "info",
  failed: "crit",
  void: "crit",
};

export function StatusPill({ status }: { status: string }) {
  return <Pill tone={STATUS_TONES[status] ?? "neutral"}>{status.replace(/_/g, " ")}</Pill>;
}

const DECISION_TONES: Record<string, Tone> = {
  ALLOW: "ok",
  REQUIRE_APPROVAL: "warn",
  REJECT: "crit",
  NOOP: "neutral",
};

export function DecisionPill({ decision }: { decision: string }) {
  return <Pill tone={DECISION_TONES[decision] ?? "neutral"}>{decision}</Pill>;
}
