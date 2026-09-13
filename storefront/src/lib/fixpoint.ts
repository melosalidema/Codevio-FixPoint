/**
 * Client for the Fixpoint control-plane API.
 *
 * The storefront never moves money itself. It submits the customer's refund
 * request as a run and then reads the run's status: Fixpoint's deterministic
 * gateway, human approval and independent verifier do the rest.
 */

import { usd } from "./format";

export type RunStatus = "completed" | "awaiting_approval" | "denied" | "failed" | "pending" | string;

export type Envelope = {
  max_refund_cents: number;
  approval_threshold_cents: number;
  auto_approve_cents: number;
  team_lead_cents: number;
  dual_approval_cents: number;
  max_actions_per_run: number;
};

export type FixpointConfig = {
  demo_mode: boolean;
  env: string;
  version: string;
  default_tenant_id: string;
  llm_enabled: boolean;
  llm_model: string;
  provider_backend: string;
  envelope: Envelope;
};

export type CheckResult = { name: string; passed: boolean; detail: string };

export type RunVerification = {
  run_id: string;
  passed: boolean;
  checks: CheckResult[];
  unsafe_mutations: number;
  synced_systems: string[];
};

export type ProposedAction = {
  tool: string;
  params: Record<string, unknown>;
  justification: string;
  evidence_refs: string[];
};

export type ApprovalArtifact = {
  run_id: string;
  tenant_id: string;
  action: ProposedAction;
  action_hash: string;
  amount_cents: number;
  required_role: string;
  required_approvals: number;
  separation_of_duties: boolean;
  facts: Record<string, unknown>;
  untrusted_justification: string;
  status: string;
};

export type ChargeState = { status: string; refunded_cents: number; amount_cents: number };

export type WorldSnapshot = {
  charges: Record<string, ChargeState>;
  contacts: Record<string, unknown>;
  drafts: { id: string; to: string; sent: boolean }[];
  slack: Record<string, unknown>[];
};

export type RunReport = {
  run_id: string;
  status: RunStatus;
  outcome: string;
  verified: boolean;
  unsafe_blocked: number;
  report_text: string;
  claims: string[];
  grounded_claims: string[];
  ungrounded_claims: string[];
};

export type RunDetail = {
  run_id: string;
  tenant_id: string;
  status: RunStatus;
  outcome: string;
  verified: boolean;
  unsafe_blocked: number;
  request_text: string;
  created_at?: string | null;
  report?: RunReport | null;
  verification?: RunVerification | null;
  approval_artifact?: ApprovalArtifact | null;
  world_before?: WorldSnapshot | null;
  world_after?: WorldSnapshot | null;
  planner_source?: string;
  provider_backend?: string;
  audit?: { chain_ok: boolean; reason: string };
};

export type RefundRunInput = {
  requestText: string;
  amountCents: number;
  stripeRefundFailures?: number;
  duplicateCustomer?: boolean;
};

const API_BASE = import.meta.env.VITE_FIXPOINT_API_BASE ?? "";
export const CONSOLE_URL = import.meta.env.VITE_FIXPOINT_CONSOLE_URL ?? "http://localhost:5173";

export class FixpointError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "FixpointError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
      },
    });
  } catch {
    throw new FixpointError(0, "Fixpoint API is unreachable — is the backend running on port 8000?");
  }

  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      detail = await response.text().catch(() => "");
    }
    throw new FixpointError(response.status, detail || response.statusText);
  }
  return (await response.json()) as T;
}

export const fixpoint = {
  config: () => request<FixpointConfig>("/api/config"),

  createRefundRun: (input: RefundRunInput) =>
    request<RunDetail>("/api/runs", {
      method: "POST",
      body: JSON.stringify({
        request_text: input.requestText,
        amount_cents: input.amountCents,
        stripe_refund_failures: input.stripeRefundFailures ?? 0,
        duplicate_customer: input.duplicateCustomer ?? false,
      }),
    }),

  getRun: (runId: string) => request<RunDetail>(`/api/runs/${runId}`),
};

export function runUrl(runId: string): string {
  return `${CONSOLE_URL}/runs/${runId}`;
}

/** True when the verifier confirmed the refund actually happened. */
export function isRefundSettled(run: RunDetail | undefined): boolean {
  if (!run) return false;
  if (run.status !== "completed") return false;
  if (!run.verified) return false;
  return run.outcome === "completed" || run.outcome === "completed_after_approval";
}

export type RunView = {
  tone: "success" | "pending" | "danger" | "neutral";
  title: string;
  detail: string;
  moneyMoved: boolean;
};

/** Human-readable interpretation of the run's outcome, for the customer. */
export function describeRun(run: RunDetail): RunView {
  const amount = run.approval_artifact?.amount_cents ?? 0;

  // A rejected action also opens an escalation artifact, so the run can be
  // "awaiting_approval" while zero money moved. Unsafe-blocked wins the label.
  if (run.unsafe_blocked > 0) {
    return {
      tone: "danger",
      title: "Blocked as unsafe",
      detail:
        "The deterministic gateway rejected the action (for example a refund redirected to a new destination) and logged an unsafe-blocked event. Zero money moved; the escalation is recorded for human review.",
      moneyMoved: false,
    };
  }

  if (run.status === "awaiting_approval" || run.outcome === "awaiting_human_approval") {
    return {
      tone: "pending",
      title: "Waiting for operator approval",
      detail: `The agent prepared the ${usd(amount)} refund and stopped before moving money. A human operator must approve it in the Fixpoint console.`,
      moneyMoved: false,
    };
  }

  switch (run.outcome) {
    case "completed":
    case "completed_after_approval":
      return {
        tone: "success",
        title: run.verified ? "Refund issued and verified" : "Refund issued",
        detail: run.verified
          ? "The verifier re-read the payment provider and confirmed exactly one refund for the approved amount."
          : "The refund executed, but the independent verification did not pass.",
        moneyMoved: true,
      };
    case "unsafe_blocked":
      return {
        tone: "danger",
        title: "Blocked by the safety gateway",
        detail:
          "The request attempted something outside the policy (for example redirecting money to a new destination). No money moved.",
        moneyMoved: false,
      };
    case "ambiguous_identity_escalated":
      return {
        tone: "danger",
        title: "Escalated: ambiguous customer identity",
        detail: "More than one customer record matches this request, so the agent refused to guess.",
        moneyMoved: false,
      };
    case "no_actionable_remedy":
      return {
        tone: "neutral",
        title: "No actionable remedy found",
        detail: "The agent could not tie this request to a charge it is allowed to refund.",
        moneyMoved: false,
      };
    case "denied_by_human":
      return {
        tone: "danger",
        title: "Denied by an operator",
        detail: "A human reviewed the proposal and declined. No money moved.",
        moneyMoved: false,
      };
    case "approval_rejected_role":
      return {
        tone: "danger",
        title: "Approval rejected: wrong role",
        detail: "The approval came from an operator without the required role. No money moved.",
        moneyMoved: false,
      };
    case "approval_rejected_sod":
      return {
        tone: "danger",
        title: "Approval rejected: separation of duties",
        detail: "The same person cannot request and approve the money action. No money moved.",
        moneyMoved: false,
      };
    case "approval_voided":
      return {
        tone: "danger",
        title: "Approval voided",
        detail: "The action changed after approval, so the token was voided. No money moved.",
        moneyMoved: false,
      };
    default:
      return {
        tone: run.status === "failed" ? "danger" : "neutral",
        title: run.status === "failed" ? "Run failed" : "Refund run finished",
        detail: run.report?.report_text || `Outcome: ${run.outcome}`,
        moneyMoved: false,
      };
  }
}
