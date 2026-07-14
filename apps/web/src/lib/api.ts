// The one place the UI talks to the network. Only the control plane, never providers.
import type {
  AgendaResponse,
  Approval,
  Artifact,
  ArtifactContent,
  Briefing,
  CommandRequest,
  Connector,
  ConnectorTool,
  DoctorReport,
  Domain,
  KnowledgeResult,
  Memory,
  OnboardingRequest,
  PersonItem,
  Policy,
  ProjectItem,
  ProvidersResponse,
  Run,
  RunEvent,
  Schedule,
  SecretsResponse,
  Session,
  SettingsResponse,
  Skill,
  UsageResponse,
} from "@/lib/types";

// Resolve the control-plane base URL. If NEXT_PUBLIC_API_URL is set it wins (deploys, e2e).
// Otherwise, in the browser, use the SAME host the page was served from with the control-plane
// port — so reaching the cockpit from another device (a phone over Tailscale/LAN) needs zero
// per-device config: "localhost" on a phone is the phone, but window.location.hostname is the
// machine actually running Otto. Falls back to localhost during SSR / tests.
function resolveApiUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
  if (configured) return configured;
  if (typeof window !== "undefined" && window.location?.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8787`;
  }
  return "http://localhost:8787";
}

export const API_URL = resolveApiUrl();

export class ApiError extends Error {
  status: number;
  correlationId?: string;
  constructor(status: number, message: string, correlationId?: string) {
    super(message);
    this.status = status;
    this.correlationId = correlationId;
  }
}

function correlationId(): string {
  return `cor_${Math.random().toString(36).slice(2, 12)}${Date.now().toString(36)}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const cid = correlationId();
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Correlation-Id": cid,
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      0,
      "Control plane unreachable — is it running? Try `make dev` and check port 8787.",
      cid,
    );
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || body.title || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail, cid);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  // system
  health: () => request<{ status: string; version: string }>("/health"),
  doctor: () => request<DoctorReport>("/doctor"),
  onboardingStatus: () =>
    request<{ completed: boolean; workspace_id?: string; user_name?: string; assistant_name?: string }>(
      "/onboarding/status",
    ),
  onboard: (body: OnboardingRequest) =>
    request<{ workspace_id: string }>("/onboarding", { method: "POST", body: JSON.stringify(body) }),
  settings: () => request<SettingsResponse>("/settings"),
  patchSettings: (body: Record<string, unknown>) =>
    request<{ ok: boolean }>("/settings", { method: "PATCH", body: JSON.stringify(body) }),
  providers: () => request<ProvidersResponse>("/providers"),
  secrets: () => request<SecretsResponse>("/secrets"),
  putSecret: (name: string, value: string) =>
    request<{ name: string; configured: boolean; source: string; shadowed_by_env: boolean }>(
      `/secrets/${encodeURIComponent(name)}`,
      { method: "PUT", body: JSON.stringify({ value }) },
    ),
  deleteSecret: (name: string) =>
    request<void>(`/secrets/${encodeURIComponent(name)}`, { method: "DELETE" }),
  domains: () => request<Domain[]>("/domains"),
  patchDomain: (key: string, body: { enabled?: boolean; read_only?: boolean }) =>
    request<Domain>(`/domains/${key}`, { method: "PATCH", body: JSON.stringify(body) }),
  policies: () => request<Policy[]>("/policies"),
  createPolicy: (body: Record<string, unknown>) =>
    request<Policy>("/policies", { method: "POST", body: JSON.stringify(body) }),
  deletePolicy: (id: string) => request<void>(`/policies/${id}`, { method: "DELETE" }),
  usage: () => request<UsageResponse>("/usage"),

  // cockpit data
  briefing: () => request<Briefing>("/briefing"),
  agenda: () => request<AgendaResponse>("/agenda"),
  projects: () => request<ProjectItem[]>("/projects"),
  people: () => request<PersonItem[]>("/people"),
  knowledgeSearch: (q: string) =>
    request<KnowledgeResult>(`/knowledge/search?q=${encodeURIComponent(q)}`),
  knowledgeReindex: () => request<{ indexed: number }>("/knowledge/reindex", { method: "POST" }),

  // runs & commands
  submitCommand: (body: CommandRequest) =>
    request<Run>("/commands", { method: "POST", body: JSON.stringify(body) }),
  runs: (params?: { status?: string; kind?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.kind) q.set("kind", params.kind);
    if (params?.limit) q.set("limit", String(params.limit));
    return request<Run[]>(`/runs?${q}`);
  },
  run: (id: string) => request<Run>(`/runs/${id}`),
  runEvents: (id: string, since = 0) => request<RunEvent[]>(`/runs/${id}/events?since=${since}`),
  cancelRun: (id: string) => request<Run>(`/runs/${id}/cancel`, { method: "POST" }),
  interruptRun: (id: string) => request<Run>(`/runs/${id}/interrupt`, { method: "POST" }),
  resumeRun: (id: string) => request<Run>(`/runs/${id}/resume`, { method: "POST" }),
  sessions: () => request<Session[]>("/sessions"),
  sessionRuns: (id: string) => request<Run[]>(`/sessions/${id}/runs`),

  // approvals
  approvals: (status?: string) =>
    request<Approval[]>(`/approvals${status ? `?status=${status}` : ""}`),
  resolveApproval: (
    id: string,
    body: { decision: "approve" | "deny"; note?: string; confirm_phrase?: string },
  ) => request<Approval>(`/approvals/${id}/resolve`, { method: "POST", body: JSON.stringify(body) }),

  // skills
  skills: () => request<Skill[]>("/skills"),
  skill: (slug: string) => request<Skill>(`/skills/${slug}`),
  patchSkill: (slug: string, body: { autonomy?: number; enabled?: boolean }) =>
    request<Skill>(`/skills/${slug}`, { method: "PATCH", body: JSON.stringify(body) }),
  runSkill: (slug: string, body?: { input?: Record<string, unknown>; mode?: string }) =>
    request<Run>(`/skills/${slug}/run`, { method: "POST", body: JSON.stringify(body ?? {}) }),

  // connectors
  connectors: () => request<Connector[]>("/connectors"),
  connector: (slug: string) => request<Connector>(`/connectors/${slug}`),
  connectorTools: (slug: string) => request<ConnectorTool[]>(`/connectors/${slug}/tools`),
  checkConnectorHealth: (slug: string) =>
    request<Connector>(`/connectors/${slug}/health`, { method: "POST" }),
  patchConnector: (slug: string, body: Record<string, unknown>) =>
    request<Connector>(`/connectors/${slug}`, { method: "PATCH", body: JSON.stringify(body) }),
  registerConnector: (body: Record<string, unknown>) =>
    request<Connector>("/connectors", { method: "POST", body: JSON.stringify(body) }),
  removeConnectorResource: (slug: string, name: string) =>
    request<Connector>(
      `/connectors/${slug}/resources/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),

  // automations
  automations: () => request<Schedule[]>("/automations"),
  createAutomation: (body: Record<string, unknown>) =>
    request<Schedule>("/automations", { method: "POST", body: JSON.stringify(body) }),
  patchAutomation: (id: string, body: Record<string, unknown>) =>
    request<Schedule>(`/automations/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  runAutomationNow: (id: string, shadow?: boolean) =>
    request<Run>(
      `/automations/${id}/run-now${shadow !== undefined ? `?shadow=${shadow}` : ""}`,
      { method: "POST" },
    ),

  // artifacts & memories
  artifacts: (runId?: string) =>
    request<Artifact[]>(`/artifacts${runId ? `?run_id=${runId}` : ""}`),
  artifact: (id: string) => request<ArtifactContent>(`/artifacts/${id}`),
  artifactDownloadUrl: (id: string) => `${API_URL}/api/v1/artifacts/${id}/download`,
  memories: (status?: string) => request<Memory[]>(`/memories${status ? `?status=${status}` : ""}`),
  reviewMemory: (id: string, body: { action: "approve" | "reject"; content?: string }) =>
    request<Memory>(`/memories/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteMemory: (id: string) => request<void>(`/memories/${id}`, { method: "DELETE" }),
  memoriesExportUrl: () => `${API_URL}/api/v1/memories/export`,
};
