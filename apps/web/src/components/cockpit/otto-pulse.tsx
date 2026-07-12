"use client";

// The Otto pulse encodes real system state (never decoration). With reduced
// motion, animation stops and the label alone carries the state (UX_SPEC).
import { cn } from "@/lib/utils";
import type { OttoState } from "@/lib/types";

const STATE_META: Record<OttoState, { label: string; className: string; color: string }> = {
  idle: { label: "Ready", className: "otto-idle", color: "var(--accent)" },
  listening: { label: "Listening", className: "otto-idle", color: "var(--accent)" },
  thinking: { label: "Thinking", className: "otto-thinking", color: "var(--accent)" },
  acting: { label: "Working", className: "otto-acting", color: "var(--accent)" },
  waiting: { label: "Waiting for your approval", className: "otto-waiting", color: "var(--warn)" },
  completed: { label: "Done", className: "otto-completed", color: "var(--accent)" },
  error: { label: "Needs attention", className: "otto-error", color: "var(--danger)" },
};

export function OttoPulse({
  state,
  size = 72,
  showLabel = true,
  className,
}: {
  state: OttoState;
  size?: number;
  showLabel?: boolean;
  className?: string;
}) {
  const meta = STATE_META[state];
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
        {/* soft halo */}
        <circle cx="50" cy="50" r="46" fill={meta.color} opacity="0.08" />
        {/* orbit rings (thinking) */}
        <g className="otto-ring-1" style={{ transformOrigin: "50px 50px" }}>
          <circle
            cx="50" cy="50" r="38" fill="none" stroke={meta.color} strokeWidth="1.5"
            strokeDasharray="10 50" strokeLinecap="round"
            opacity={state === "thinking" ? 0.7 : 0}
          />
        </g>
        <g className="otto-ring-2" style={{ transformOrigin: "50px 50px" }}>
          <circle
            cx="50" cy="50" r="32" fill="none" stroke={meta.color} strokeWidth="1.5"
            strokeDasharray="6 40" strokeLinecap="round"
            opacity={state === "thinking" ? 0.5 : 0}
          />
        </g>
        {/* acting sweep */}
        <circle
          className="otto-sweep"
          cx="50" cy="50" r="41" fill="none" stroke={meta.color} strokeWidth="2.5"
          strokeDasharray="70 190" strokeLinecap="round"
          opacity={state === "acting" ? 0.85 : 0}
        />
        {/* error alert ring */}
        <circle
          className="otto-alert"
          cx="50" cy="50" r="42" fill="none" stroke={meta.color} strokeWidth="2"
          opacity={state === "error" ? 0.8 : 0}
        />
        {/* core */}
        <g className="otto-core" style={{ transformOrigin: "50px 50px" }}>
          <circle cx="50" cy="50" r="22" fill={meta.color} opacity="0.9" />
          <circle cx="50" cy="50" r="22" fill="url(#ottoShine)" />
          <circle cx="50" cy="50" r="27" fill="none" stroke={meta.color} strokeWidth="1" opacity="0.35" />
        </g>
        <defs>
          <radialGradient id="ottoShine" cx="0.35" cy="0.3" r="0.9">
            <stop offset="0%" stopColor="white" stopOpacity="0.55" />
            <stop offset="60%" stopColor="white" stopOpacity="0.05" />
            <stop offset="100%" stopColor="white" stopOpacity="0" />
          </radialGradient>
        </defs>
      </svg>
      {showLabel ? (
        <span
          aria-live="polite"
          data-testid="otto-state"
          className={cn(
            "text-xs font-medium",
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
