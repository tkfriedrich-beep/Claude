// Friendly aliases over the OpenAPI-generated contract (packages/contracts).
// Do not hand-edit shapes that exist in the contract — regenerate with `make contracts`.
import type { components } from "@agenticos/contracts";

export type Run = components["schemas"]["RunOut"];
export type RunEvent = components["schemas"]["EventOut"];
export type Approval = components["schemas"]["ApprovalOut"];
export type Skill = components["schemas"]["SkillOut"];
export type Connector = components["schemas"]["ConnectorOut"];
export type ConnectorTool = components["schemas"]["ConnectorToolOut"];
export type Artifact = components["schemas"]["ArtifactOut"];
export type Memory = components["schemas"]["MemoryOut"];
export type Schedule = components["schemas"]["ScheduleOut"];
export type Session = components["schemas"]["SessionOut"];
export type Domain = components["schemas"]["DomainOut"];
export type Policy = components["schemas"]["PolicyOut"];
export type CommandRequest = components["schemas"]["CommandRequest"];
export type OnboardingRequest = components["schemas"]["OnboardingRequest"];

// Endpoints returning shaped dicts (briefing/agenda/settings/doctor) are typed here.
export interface Briefing {
  user_name: string | null;
  assistant_name: string;
  now: string;
  safe_mode: boolean;
  kill_switch: boolean;
  demo_mode: boolean;
  what_matters: { kind: string; text: string; href: string }[];
  approvals: {
    pending: number;
    items: { id: string; title: string; risk_level: string; requested_at: string }[];
  };
  active_runs: { id: string; title: string; status: string; kind: string; skill_slug: string | null }[];
  recent_runs: { id: string; title: string; status: string; finished_at: string | null }[];
  suggestions: { skill: string; label: string }[];
  skills: { slug: string; name: string; description: string; autonomy: number; risk_level: string }[];
  agenda: { events: AgendaEvent[]; demo: boolean };
  projects: { id: string; name: string; status: string; updated_at: string }[];
  metrics: {
    runs_today: number;
    approvals_pending: number;
    artifacts_week: number;
    connectors_ok: number;
    connectors_total: number;
  };
  connector_health: { slug: string; name: string; health: string; mode: string; enabled: boolean }[];
}

export interface AgendaEvent {
  id: string;
  title: string;
  start: string;
  end?: string;
  demo?: boolean;
}

export interface AgendaResponse {
  events: AgendaEvent[];
  events_demo: boolean;
  commitments: { id: string; title: string; due_at: string | null; source_ref: string | null }[];
}

export interface SettingsResponse {
  workspace_id: string;
  user_name: string | null;
  assistant_name: string;
  safe_mode: boolean;
  kill_switch: boolean;
  demo_mode: boolean;
  theme: string;
  default_mode: "read_only" | "draft" | "act";
  provider: string;
  vault_path: string | null;
  bizideas_path: string | null;
  daily_budget_usd: number;
  run_budget_usd: number;
  data_dir: string;
  providers: Record<string, { available: boolean; detail: string }>;
  skills_loaded: number;
}

export interface DoctorReport {
  status: "ok" | "warn" | "fail";
  summary: string;
  checks: { name: string; status: "ok" | "warn" | "fail"; detail: string; fix: string }[];
}

export interface ProjectItem {
  id: string;
  name: string;
  slug: string;
  status: string;
  domain_key: string;
  path: string | null;
  description: string;
  updated_at: string;
}

export interface PersonItem {
  id: string;
  name: string;
  relation: string;
  notes: string;
  source_ref: string | null;
}

export interface KnowledgeResult {
  query: string;
  results: { path: string; title: string; snippet: string }[];
}

export interface ArtifactContent {
  id: string;
  run_id: string;
  kind: string;
  title: string;
  mime: string;
  meta: Record<string, unknown>;
  created_at: string;
  content: string | null;
  missing_file: boolean;
}

export interface UsageResponse {
  today: { runs: number; cost_usd: number; tokens_in: number; tokens_out: number; tool_calls: number };
  week: { runs: number; cost_usd: number; tokens_in: number; tokens_out: number; tool_calls: number };
  budgets: { daily_usd: number; per_run_usd: number };
}

export type OttoState =
  | "idle"
  | "listening"
  | "thinking"
  | "acting"
  | "waiting"
  | "completed"
  | "error";

export const RISK_LABEL: Record<string, string> = {
  R0: "Local read",
  R1: "External read",
  R2: "Local write",
  R3: "External write",
  R4: "High impact",
};

export const AUTONOMY_LABEL: Record<number, string> = {
  0: "Off",
  1: "Observe",
  2: "Recommend",
  3: "Draft",
  4: "Act with approval",
  5: "Act within allowlist",
};
