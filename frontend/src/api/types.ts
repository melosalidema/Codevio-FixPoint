// Wire types mirroring the FastAPI schemas exactly.

export interface Customer {
  id: string;
  email: string;
  name: string;
}

export interface ChargeFact {
  id: string;
  customer_id: string;
  amount_cents: number;
  status: string;
  refunded_cents: number;
}

export interface ProposedAction {
  tool: string;
  params: Record<string, unknown>;
  justification: string;
  evidence_refs: string[];
}

export interface ApprovalArtifact {
  run_id: string;
  tenant_id: string;
  action: ProposedAction;
  action_hash: string;
  amount_cents: number;
  required_role: string;
  required_approvals: number;
  separation_of_duties: boolean;
  facts: {
    customers?: Customer[];
    charges?: ChargeFact[];
    policy_hash?: string;
  };
  untrusted_justification: string;
  status: "pending" | "approved" | "denied" | "void";
}

export interface CheckResult {
  name: string;
  passed: boolean;
  detail: string;
}

export interface Verification {
  passed: boolean;
  checks: CheckResult[];
  unsafe_mutations: number;
  synced_systems: string[];
}

export interface RunReport {
  status: string;
  outcome: string;
  verified: boolean;
  unsafe_blocked: number;
  approval_artifact: ApprovalArtifact | null;
  report_text: string;
  claims: string[];
  grounded_claims: string[];
  ungrounded_claims: string[];
}

export interface WorldSnapshot {
  charges: Record<string, { status: string; refunded_cents: number; amount_cents: number }>;
  contacts: Record<string, { status: string; notes: number; owner: string }>;
  drafts: { id: string; to: string; sent: boolean }[];
  slack: { tenant_id: string; channel: string; text: string }[];
}

export interface AuditEntry {
  seq: number;
  run_id: string;
  type: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  hash: string;
}

export interface AuditResponse {
  chain_ok: boolean;
  reason: string;
  entries: AuditEntry[];
}

export interface RunDetail {
  run_id: string;
  tenant_id: string;
  status: string;
  outcome: string;
  verified: boolean;
  unsafe_blocked: number;
  request_text: string;
  created_at: string | null;
  report: RunReport | null;
  verification: Verification | null;
  approval_artifact: ApprovalArtifact | null;
  world_before: WorldSnapshot | null;
  world_after: WorldSnapshot | null;
  planner_source: string;
  provider_backend: string;
  planner_meta: Record<string, unknown> | null;
  audit: AuditResponse;
}

export interface RunSummary {
  run_id: string;
  tenant_id: string;
  status: string;
  outcome: string;
  verified: boolean;
  unsafe_blocked: number;
  request_text: string;
  created_at: string | null;
}

export interface Envelope {
  max_refund_cents: number;
  approval_threshold_cents: number;
  auto_approve_cents: number;
  team_lead_cents: number;
  dual_approval_cents: number;
  max_actions_per_run: number;
}

export interface ConfigResponse {
  demo_mode: boolean;
  env: string;
  version: string;
  default_tenant_id: string;
  llm_enabled: boolean;
  provider_backend: string;
  envelope: Envelope;
}

export interface Scenario {
  id: string;
  title: string;
  flow: string;
  request: string | null;
  expect: Record<string, unknown>;
}

export interface ScenarioResult {
  id: string;
  title: string;
  passed: boolean;
  observed: Record<string, unknown>;
  failed: string[];
}

export interface EvalRun {
  batch_id: string;
  total: number;
  passed: number;
  unsafe_blocked: number;
  results: ScenarioResult[];
}

export interface EvalResults {
  batch_id: string | null;
  total: number;
  passed: number;
  unsafe_blocked: number;
  results: ScenarioResult[];
}

export interface RunCreateRequest {
  request_text: string;
  amount_cents: number;
  duplicate_customer: boolean;
  stripe_refund_failures: number;
}

export interface DecisionRequest {
  approver_user_id: string;
  role: "team_lead" | "finance" | "finance_dual";
}
