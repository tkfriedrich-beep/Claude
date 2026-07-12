"use client";

// Right rail: Otto pulse, active run with controls, approvals shortcut, and the
// human-readable live timeline. Raw payloads stay behind "Technical details".
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useLiveEvents } from "@/lib/events";
import { ACTIVE_RUN_STATUSES, cn, fmtTime, RUN_STATUS_STYLE } from "@/lib/utils";
import { deriveOttoState, OttoPulse } from "@/components/cockpit/otto-pulse";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";

export function ActivityRail({ open, onToggle }: { open: boolean; onToggle: () => void }) {
  const queryClient = useQueryClient();
  const { recent, connected } = useLiveEvents();
  const { data: onboarding } = useQuery({ queryKey: ["onboarding"], queryFn: api.onboardingStatus });
  const enabled = onboarding?.completed === true;
  const { data: activeRuns } = useQuery({
    queryKey: ["runs", "active"],
    queryFn: () => api.runs({ status: ACTIVE_RUN_STATUSES.join(",") }),
    enabled,
    refetchInterval: 15_000,
  });
  const { data: pending } = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => api.approvals("pending"),
    enabled,
  });

  const cancel = useMutation({
    mutationFn: (id: string) => api.cancelRun(id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["runs"] }),
  });

  const runs = activeRuns ?? [];
  const ottoState = deriveOttoState(runs, pending?.length ?? 0);

  return (
    <aside
      aria-label="Activity"
      className={cn(
        "fixed inset-y-0 right-0 z-40 w-[300px] border-l border-line bg-surface/95 backdrop-blur",
        "flex-col px-4 py-5 transition-transform xl:sticky xl:top-0 xl:h-dvh xl:translate-x-0 xl:flex",
        open ? "flex translate-x-0 shadow-2xl" : "hidden xl:flex",
      )}
    >
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-muted">Activity</h2>
        <div className="flex items-center gap-2">
          <span
            role="status"
            aria-label={connected ? "Live" : "Reconnecting"}
            title={connected ? "Live event stream connected" : "Reconnecting…"}
            className={cn("size-2 rounded-full", connected ? "bg-accent" : "bg-warn")}
          />
          <button onClick={onToggle} aria-label="Close activity rail" className="text-muted xl:hidden">
            <X className="size-4" />
          </button>
        </div>
      </div>

      <div className="flex justify-center py-3">
        <OttoPulse state={ottoState} size={84} />
      </div>

      {pending && pending.length > 0 ? (
        <Link
          href="/approvals"
          className="mb-3 flex items-center justify-between rounded-[10px] border border-warn/40 bg-warn-soft px-3 py-2.5 text-[13px] font-medium text-warn"
        >
          {pending.length} approval{pending.length > 1 ? "s" : ""} waiting
          <span aria-hidden>→</span>
        </Link>
      ) : null}

      {runs.length > 0 ? (
        <div className="mb-3 space-y-2">
          {runs.slice(0, 3).map((run) => {
            const style = RUN_STATUS_STYLE[run.status] ?? { label: run.status, tone: "muted" as const };
            return (
              <div key={run.id} className="rounded-[10px] border border-line bg-raised p-3">
                <div className="flex items-center justify-between gap-2">
                  <Link href={`/history/${run.id}`} className="truncate text-[13px] font-medium hover:text-accent">
                    {run.title}
                  </Link>
                  <Badge tone={style.tone}>{style.label}</Badge>
                </div>
                <div className="mt-2 flex gap-1.5">
                  <Button size="sm" variant="ghost" onClick={() => cancel.mutate(run.id)}>
                    Cancel
                  </Button>
                  {run.status === "awaiting_approval" ? (
                    <Link href="/approvals">
                      <Button size="sm" variant="warn">Review</Button>
                    </Link>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      <h3 className="mb-1.5 text-[12px] font-semibold uppercase tracking-wide text-muted">Timeline</h3>
      <ol className="rail-scroll min-h-0 flex-1 space-y-2 overflow-y-auto pr-1" aria-live="polite">
        {recent.length === 0 ? (
          <li className="text-[13px] text-muted">
            Quiet so far. Events appear here as Otto works.
          </li>
        ) : (
          recent.map((event) => (
            <li key={event.id} className="rounded-lg border border-line/70 bg-surface px-2.5 py-2">
              <p className="text-[12.5px] leading-snug">{event.human_text}</p>
              <div className="mt-1 flex items-center justify-between">
                <Link href={`/history/${event.run_id}`} className="font-mono text-[10.5px] text-muted hover:text-accent">
                  {event.run_id.slice(0, 14)}…
                </Link>
                <time className="font-mono text-[10.5px] text-muted">{fmtTime(event.ts)}</time>
              </div>
            </li>
          ))
        )}
      </ol>
    </aside>
  );
}
