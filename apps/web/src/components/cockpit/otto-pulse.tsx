"use client";

// The Otto pulse encodes real system state (never decoration) — OttoOS spec §02.
// One champagne-gold orb, seven states; with reduced motion the label alone carries
// the state. Announced via aria-live.
import { cn } from "@/lib/utils";
import type { OttoState } from "@/lib/types";

export const OTTO_STATUS: Record<
  OttoState,
  { label: string; sub: string; className: string; color: string }
> = {
  idle: {
    label: "Steady — watching the periphery",
    sub: "Nothing needs you right now.",
    className: "otto-idle",
    color: "var(--ink-soft)",
  },
  listening: {
    label: "Listening",
    sub: "Go ahead — Otto is paying attention.",
    className: "otto-listening",
    color: "var(--accent-hover)",
  },
  thinking: {
    label: "Thinking",
    sub: "Weighing sources before acting.",
    className: "otto-thinking",
    color: "var(--accent-hover)",
  },
  acting: {
    label: "Working",
    sub: "Executing within the grants you set.",
    className: "otto-acting",
    color: "var(--accent-hover)",
  },
  waiting: {
    label: "Waiting on your judgment",
    sub: "Approvals are queued — nothing executes without you.",
    className: "otto-waiting",
    color: "var(--warn)",
  },
  completed: {
    label: "Complete",
    sub: "Finished work settled into the archive.",
    className: "otto-completed",
    color: "var(--accent-hover)",
  },
  error: {
    label: "Needs attention",
    sub: "Something halted — calm, never flashing.",
    className: "otto-error",
    color: "var(--danger)",
  },
};

export function OttoPulse({
  state,
  size = 56,
  showLabel = true,
  className,
}: {
  state: OttoState;
  size?: number;
  showLabel?: boolean;
  className?: string;
}) {
  const meta = OTTO_STATUS[state];
  const halted = state === "error";
  return (
    <div className={cn("flex flex-col items-center gap-1.5", className)}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        className={cn("otto-orb", meta.className)}
        aria-hidden
        data-otto-state={state}
      >
        {/* soft gold glow */}
        <circle cx="50" cy="50" r="47" fill="var(--accent)" opacity="0.10" />
        {/* orbit rings — thinking (counter-orbits 2.6s/3.9s) and acting (single sweep 1.05s) */}
        <g className="otto-ring-1" style={{ transformOrigin: "50px 50px" }}>
          <circle
            cx="50" cy="50" r="40" fill="none" stroke="var(--accent)" strokeWidth="1.5"
            strokeDasharray="16 236" strokeLinecap="round"
            opacity={state === "thinking" ? 0.8 : state === "acting" ? 0.9 : 0}
          />
        </g>
        <g className="otto-ring-2" style={{ transformOrigin: "50px 50px" }}>
          <circle
            cx="50" cy="50" r="34" fill="none" stroke="var(--accent)" strokeWidth="1.5"
            strokeDasharray="10 204" strokeLinecap="round"
            opacity={state === "thinking" ? 0.5 : 0}
          />
        </g>
        {/* judgment amber ring — waiting; steady danger ring — halted */}
        <circle
          className="otto-alert"
          cx="50" cy="50" r="43" fill="none"
          stroke={halted ? "var(--danger)" : "var(--warn)"} strokeWidth="1.5"
          opacity={state === "waiting" ? 0.65 : halted ? 0.6 : 0}
        />
        {/* champagne sphere core (spec §02 gradient) */}
        <g
          className="otto-core"
          style={{ transformOrigin: "50px 50px" }}
          opacity={halted ? 0.35 : 1}
          filter={halted ? "grayscale(0.8)" : undefined}
        >
          <circle cx="50" cy="50" r="27" fill="url(#ottoSphere)" />
          <circle
            cx="50" cy="50" r="28" fill="none"
            stroke="var(--accent)" strokeWidth="1" opacity="0.45"
          />
        </g>
        <defs>
          <radialGradient id="ottoSphere" cx="0.35" cy="0.3" r="0.95">
            <stop offset="0%" stopColor="#f0d9a4" />
            <stop offset="45%" stopColor="#c9a961" />
            <stop offset="78%" stopColor="#8a713c" />
            <stop offset="100%" stopColor="#4a3d22" />
          </radialGradient>
        </defs>
      </svg>
      {showLabel ? (
        <span
          aria-live="polite"
          data-testid="otto-state"
          className={cn(
            "text-center text-xs font-medium",
            state === "waiting" ? "text-warn" : state === "error" ? "text-danger" : "text-muted",
          )}
        >
          {meta.label}
        </span>
      ) : (
        <span className="sr-only" aria-live="polite">{meta.label}</span>
      )}
    </div>
  );
}

export function deriveOttoState(runs: { status: string }[], pendingApprovals: number): OttoState {
  if (pendingApprovals > 0 || runs.some((r) => r.status === "awaiting_approval")) return "waiting";
  if (runs.some((r) => r.status === "executing")) return "acting";
  if (runs.some((r) => ["triaging", "planning", "verifying", "reviewing"].includes(r.status)))
    return "thinking";
  if (runs.some((r) => r.status === "queued")) return "thinking";
  return "idle";
}
