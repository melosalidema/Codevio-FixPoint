import type {
  AuditResponse,
  ConfigResponse,
  DecisionRequest,
  EvalResults,
  EvalRun,
  RunCreateRequest,
  RunDetail,
  RunSummary,
  Scenario,
  ScenarioResult,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail ? `${status}: ${detail}` : String(status));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(0, "network unreachable – is the API running?");
  }

  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      detail = await response.text().catch(() => "");
    }
    throw new ApiError(response.status, detail || response.statusText);
  }
  return (await response.json()) as T;
}

export const api = {
  config: () => request<ConfigResponse>("/api/config"),

  createRun: (body: RunCreateRequest) =>
    request<RunDetail>("/api/runs", { method: "POST", body: JSON.stringify(body) }),

  listRuns: () => request<RunSummary[]>("/api/runs"),

  getRun: (runId: string) => request<RunDetail>(`/api/runs/${runId}`),

  approve: (runId: string, body: DecisionRequest) =>
    request<RunDetail>(`/api/runs/${runId}/approve`, { method: "POST", body: JSON.stringify(body) }),

  deny: (runId: string, body: DecisionRequest) =>
    request<RunDetail>(`/api/runs/${runId}/deny`, { method: "POST", body: JSON.stringify(body) }),

  audit: (runId: string) => request<AuditResponse>(`/api/runs/${runId}/audit`),

  tamper: (runId: string) =>
    request<AuditResponse>(`/api/runs/${runId}/audit/tamper`, { method: "POST" }),

  scenarios: () =>
    request<{ scenarios: Scenario[] }>("/api/scenarios").then((data) => data.scenarios),

  runScenario: (scenarioId: string) =>
    request<ScenarioResult>(`/api/scenarios/${scenarioId}/run`, { method: "POST" }),

  runEvals: () => request<EvalRun>("/api/evals/run", { method: "POST" }),

  evalResults: () => request<EvalResults>("/api/evals/results"),
};
