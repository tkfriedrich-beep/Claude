"use client";

// Ambient rail (OttoOS spec §05): ACTIVITY + live dot · orb 52 + status · amber decisions
// card · mini decision cards (inline Deny / Review / Approve) · LIVE TIMELINE (14 max) ·
// SYSTEMS dots · counts footer. Never competes with focused work: no motion except the
// orb; collapses in Deep Work; drawer below xl (kept).
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useLiveEvents } from "@/lib/events";
import { ACTIVE_RUN_STATUSES, cn, fmtTime } from "@/lib/utils";
import { deriveOttoState, OTTO_STATUS, OttoPulse } from "@/components/cockpit/otto-pulse";
import { useWorkMode } from "@/components/cockpit/work-mode";
import { SectionLabel } from "@/components/ui/states";
import { X } from "lucide-react";

export function ActivityRail({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const queryClient = useQueryClient();
  const { mode } = useWorkMode();
  const { recent, connected } = useLiveEvents();
  const { data: onboarding } = useQuery({ queryKey: ["onboarding"], queryFn: api.onboardingStatus });
  const enabled = onboarding?.completed === true;
  const { data: activeRuns, isError: runsError } = useQuery({
    queryKey: ["runs", "active"],
    queryFn: () => api.runs({ status: ACTIVE_RUN_STATUSES.join(",") }),
    enabled,
    refetchInterval: 15_000,
  });
  const { data: pending, isError: pendingError } = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => api.approvals("pending"),
    enabled,
    refetchInterval: 30_000,
  });
  const { data: briefing } = useQuery({
    queryKey: ["briefing"],
    queryFn: api.briefing,
    enabled,
    refetchInterval: 60_000,
  });
  const { data: usage } = useQuery({
    queryKey: ["usage"],
    queryFn: api.usage,
    enabled,
    refetchInterval: 60_000,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["approvals"] });
    queryClient.invalidateQueries({ queryKey: ["runs"] });
    queryClient.invalidateQueries({ queryKey: ["briefing"] });
  };
  const resolve = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "deny" }) =>
      api.resolveApproval(id, { decision }),
    onSettled: invalidate,
  });

  const runs = activeRuns ?? [];
  const queue = pending ?? [];
  const ottoState = deriveOttoState(runs, queue.length);
  const status = OTTO_STATUS[ottoState];
  // The rail is a trust surface: a failed read must not render as a calm, healthy orb (F6).
  const statusUnavailable = enabled && (runsError || pendingError);

  // Deep Work: the rail yields entirely — approvals queue silently (spec §05).
  if (mode === "deep") return null;

  return (
    <aside
      aria-label="Activity"
      className={cn(
        "fixed inset-y-0 right-0 z-40 w-[300px] border-l border-line bg-tile",
        "flex-col gap-5 overflow-y-auto px-4 py-5 transition-transform",
        "xl:sticky xl:top-0 xl:flex xl:h-dvh xl:w-[min(330px,26vw)] xl:translate-x-0",
        open ? "flex translate-x-0 shadow-2xl" : "hidden xl:flex",
      )}
    >
      <div className="flex items-center justify-between">
        <SectionLabel>Activity</SectionLabel>
        <div className="flex items-center gap-2">
          <span
            role="status"
            aria-label={connected ? "Live" : "Reconnecting"}
            title={connected ? "Live event stream connected" : "Reconnecting…"}
            className={cn("size-[7px] rounded-full", connected ? "bg-ok" : "bg-warn")}
          />
          <button onClick={onToggle} aria-label="Close activity rail" className="text-muted xl:hidden">
            <X className="size-4" />
          </button>
        </div>
      </div>

      <div className="flex flex-col items-center gap-2 text-center">
        <OttoPulse state={ottoState} size={52} showLabel={false} />
        <p
          className="text-[13px] font-medium"
          style={{ color: statusUnavailable ? "var(--muted)" : status.color }}
        >
          {statusUnavailable ? "Status unavailable" : status.label}
        </p>
      </div>

      {queue.length > 0 ? (
        <>
          <Link
            href="/approvals"
            className="flex items-center justify-between rounded-[11px] border border-(--warn-border) bg-warn-soft px-4 py-2.5 text-[13px] font-medium text-warn hover:brightness-110"
          >
            {queue.length} decision{queue.length > 1 ? "s" : ""} waiting
            <span aria-hidden>→</span>
          </Link>
          <div className="space-y-2.5">
            {queue.slice(0, 3).map((approval) => (
              <div key={approval.id} className="rounded-[11px] border border-line-card bg-surface px-4 py-3">
                <div className="flex items-baseline gap-2">
                  <p className="min-w-0 flex-1 truncate text-[13px] font-medium">{approval.title}</p>
                  <span className="shrink-0 rounded-full border border-(--warn-border) px-2 py-px font-mono text-[9px] font-medium tracking-[0.06em] text-warn">
                    NEEDS YOU
                  </span>
                </div>
                <div className="mt-2 flex gap-3.5 text-[12px] font-medium">
                  <button
                    onClick={() => resolve.mutate({ id: approval.id, decision: "deny" })}
                    className="text-muted-2 hover:text-danger"
                  >
                    Deny
                  </button>
                  <Link href="/approvals" className="text-accent-hover hover:text-accent">
                    Review →
                  </Link>
                  {!approval.confirm_phrase_required ? (
                    <button
                      onClick={() => resolve.mutate({ id: approval.id, decision: "approve" })}
                      className="ml-auto text-accent-hover hover:text-accent"
                    >
                      Approve
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </>
      ) : null}

      {runs.length > 0 ? (
        <div className="space-y-2">
          {runs.slice(0, 2).map((run) => (
            <Link
              key={run.id}
              href={`/history/${run.id}`}
              className="block truncate rounded-[11px] border border-line-card bg-surface px-4 py-2.5 text-[12.5px] text-ink-soft hover:text-ink"
            >
              <span className="text-accent-hover">▸</span> {run.title}
            </Link>
          ))}
        </div>
      ) : null}

      <div className="min-h-0">
        <SectionLabel className="mb-2">Live timeline</SectionLabel>
        <ol aria-live="polite">
          {recent.length === 0 ? (
            <li className="otto-voice py-1 text-[13.5px] text-muted">
              Quiet so far. Events appear here as Otto works.
            </li>
          ) : (
            recent.slice(0, 14).map((event) => (
              <li key={event.id} className="fadeup flex gap-3 border-b border-line-row py-2">
                <time className="w-[42px] shrink-0 font-mono text-[11px] text-faint">
                  {fmtTime(event.ts)}
                </time>
                <Link
                  href={`/history/${event.run_id}`}
                  className="min-w-0 text-[12.5px] leading-snug text-ink-soft hover:text-ink"
                >
                  {event.human_text}
                </Link>
              </li>
            ))
          )}
        </ol>
      </div>

      {briefing ? (
        <div>
          <SectionLabel className="mb-2.5">Systems</SectionLabel>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2">
            {briefing.connector_health.filter((c) => c.enabled).map((connector) => (
              <div key={connector.slug} className="flex items-center gap-2 text-[12px]">
                <span
                  aria-hidden
                  className={cn(
                    "size-1.5 shrink-0 rounded-full",
                    connector.health === "ok"
                      ? "bg-ok"
                      : connector.health === "mock"
                        ? "bg-faint"
                        : "bg-warn",
                  )}
                />
                <span className="truncate">{connector.name}</span>
                <span
                  className={cn(
                    "ml-auto font-mono text-[9.5px] uppercase",
                    connector.health === "ok" || connector.health === "mock"
                      ? "text-faint"
                      : "text-warn",
                  )}
                >
                  {connector.health === "unavailable" ? "DOWN" : connector.health.slice(0, 4)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-auto border-t border-line pt-3.5 font-mono text-[11px] leading-relaxed text-muted-2">
        {briefing ? briefing.metrics.runs_today : "—"} RUNS TODAY ·{" "}
        {usage ? `$${usage.today.cost_usd.toFixed(2)}` : "—"} SPENT
        <br />
        {briefing ? briefing.metrics.artifacts_week : "—"} ARTIFACTS THIS WEEK ·{" "}
        {pendingError ? "—" : `${queue.length} DECISION${queue.length === 1 ? "" : "S"}`} OPEN
      </div>
    </aside>
  );
}
