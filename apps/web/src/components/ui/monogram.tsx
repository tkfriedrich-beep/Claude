import { cn } from "@/lib/utils";

// OttoOS spec §03: agent identity is a monogram, not an avatar. Ring border = state.
// Status vocabulary: working · blocked · waiting · needs approval · complete · idle —
// always dot + text next to it, never color alone.
export type MonogramState = "working" | "needs" | "idle" | "done" | "blocked";

const RING: Record<MonogramState, { border: string; text: string }> = {
  working: { border: "border-(--accent-border)", text: "text-accent-hover" },
  needs: { border: "border-(--warn-border)", text: "text-warn" },
  idle: { border: "border-line-button", text: "text-ink-soft" },
  done: { border: "border-line-button", text: "text-ink-soft" },
  blocked: { border: "border-danger/50", text: "text-danger" },
};

export function Monogram({
  initials,
  state = "idle",
  size = 31,
  className,
}: {
  initials: string;
  state?: MonogramState;
  size?: number;
  className?: string;
}) {
  const ring = RING[state];
  return (
    <span
      aria-hidden
      style={{ width: size, height: size, fontSize: Math.max(9, Math.round(size * 0.36)) }}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full border font-mono font-medium",
        ring.border,
        ring.text,
        className,
      )}
    >
      {initials}
    </span>
  );
}

// Agent roster (spec §03): each agent is a 1:1 presentation of an existing skill.
export const AGENT_META: Record<string, { mono: string; name: string }> = {
  "research-run": { mono: "RS", name: "Research" },
  "decision-memo": { mono: "ST", name: "Strategy" },
  "project-pulse": { mono: "OP", name: "Operations" },
  "daily-plan": { mono: "PL", name: "Planning" },
  "morning-brief": { mono: "BR", name: "Briefing" },
  "commitment-sweep": { mono: "ME", name: "Memory" },
  "business-idea-triage": { mono: "VE", name: "Ventures" },
  "weekly-review": { mono: "RV", name: "Review" },
};

export function agentMetaFor(slug: string, name: string): { mono: string; name: string } {
  const meta = AGENT_META[slug];
  if (meta) return meta;
  const initials = name
    .split(/\s+/)
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return { mono: initials || slug.slice(0, 2).toUpperCase(), name };
}
