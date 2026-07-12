"use client";

// Replayable human-readable event timeline. Raw payloads behind "Technical details".
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { RunEvent } from "@/lib/types";
import { cn, fmtTime } from "@/lib/utils";
import { CardSkeleton, EmptyState } from "@/components/ui/states";

const TYPE_DOT: Record<string, string> = {
  "approval.required": "bg-warn",
  "approval.resolved": "bg-warn",
  "tool.failed": "bg-danger",
  "run.failed": "bg-danger",
  "run.completed": "bg-accent",
  "artifact.created": "bg-accent",
};

export function RunTimeline({ runId }: { runId: string }) {
  const { data: events, isLoading } = useQuery({
    queryKey: ["run-events", runId],
    queryFn: () => api.runEvents(runId),
    // SSE invalidation is the fast path; a light poll guarantees convergence.
    refetchInterval: 2_000,
  });

  if (isLoading) return <CardSkeleton lines={5} />;
  const visible = (events ?? []).filter((e) => e.human_text);
  if (visible.length === 0) {
    return <EmptyState title="No events yet" hint="Events appear as soon as the run starts." />;
  }
  return (
    <ol className="relative space-y-0" data-testid="run-timeline">
      {visible.map((event, i) => (
        <TimelineRow key={event.id} event={event} last={i === visible.length - 1} />
      ))}
    </ol>
  );
}

function TimelineRow({ event, last }: { event: RunEvent; last: boolean }) {
  const hasPayload = event.payload && Object.keys(event.payload).length > 0;
  return (
    <li className="relative flex gap-3 pb-4">
      {!last ? <span aria-hidden className="absolute left-[5px] top-4 h-full w-px bg-line" /> : null}
      <span
        aria-hidden
        className={cn("relative mt-1.5 size-[11px] shrink-0 rounded-full border-2 border-surface",
          TYPE_DOT[event.type] ?? "bg-line")}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-[13.5px] leading-snug">{event.human_text}</p>
          <time className="shrink-0 font-mono text-[11px] text-muted">{fmtTime(event.ts)}</time>
        </div>
        {hasPayload ? (
          <details className="mt-0.5">
            <summary className="cursor-pointer text-[11.5px] text-muted hover:text-ink">
              Technical details
            </summary>
            <pre className="mt-1 max-h-44 overflow-auto rounded-lg border border-line bg-raised p-2.5 font-mono text-[11px]">
              {JSON.stringify({ type: event.type, seq: event.seq, payload: event.payload }, null, 2)}
            </pre>
          </details>
        ) : null}
      </div>
    </li>
  );
}
