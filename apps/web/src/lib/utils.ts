import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function greeting(name: string | null | undefined, date = new Date()): string {
  const hour = date.getHours();
  const part = hour < 5 ? "Up late" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  return name ? `${part}, ${name}` : part;
}

export const RUN_STATUS_STYLE: Record<string, { label: string; tone: "accent" | "warn" | "danger" | "muted" }> = {
  queued: { label: "Queued", tone: "muted" },
  triaging: { label: "Triaging", tone: "accent" },
  planning: { label: "Planning", tone: "accent" },
  awaiting_approval: { label: "Needs approval", tone: "warn" },
  executing: { label: "Working", tone: "accent" },
  verifying: { label: "Verifying", tone: "accent" },
  reviewing: { label: "Reviewing", tone: "accent" },
  completed: { label: "Completed", tone: "accent" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "muted" },
  interrupted: { label: "Interrupted", tone: "warn" },
};

export const ACTIVE_RUN_STATUSES = [
  "queued",
  "triaging",
  "planning",
  "awaiting_approval",
  "executing",
  "verifying",
  "reviewing",
];
