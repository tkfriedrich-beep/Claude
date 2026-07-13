"use client";

// Calendar (/agenda, was Agenda) — today's events and swept commitments, straight from
// /agenda. Rows are hairline-separated ledger lines (no tiles). The spec's protected
// deep-work block is omitted until the backend grows a field for it — never fabricated.
import { useQuery } from "@tanstack/react-query";
import { Calendar } from "lucide-react";
import { api } from "@/lib/api";
import { fmtDate, fmtTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { CardSkeleton, EmptyState, ErrorState, SectionLabel } from "@/components/ui/states";

export default function CalendarPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["agenda"], queryFn: api.agenda,
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <CardSkeleton lines={4} />
        <CardSkeleton lines={3} />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="mx-auto max-w-4xl">
        <ErrorState detail={(error as Error)?.message} onRetry={() => refetch()} />
      </div>
    );
  }

  const today = new Date();

  return (
    <div className="fadeup mx-auto flex max-w-4xl flex-col gap-6">
      <header>
        <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Calendar</h1>
        <p className="mt-1 text-[13.5px] text-muted">
          Today&apos;s events and your open commitments. Calendar changes remain drafts until
          you approve them.
        </p>
      </header>

      {/* ── Today ─────────────────────────────────────────────────────────── */}
      <Card className="px-6 py-6 sm:px-8">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
          <span className="font-mono text-[11px] font-medium tracking-[2.5px] text-accent">
            {today
              .toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })
              .toUpperCase()}
          </span>
          {data.events_demo ? (
            <Badge tone="muted" className="ml-auto">
              demo data — connect Google for real events
            </Badge>
          ) : null}
        </div>
        {data.events.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              icon={<Calendar />}
              title="Nothing on the calendar today."
              hint="Connect Google Workspace in Systems to see your real calendar."
            />
          </div>
        ) : (
          <ul className="mt-2">
            {data.events.map((event) => (
              <li
                key={event.id}
                className="flex items-baseline gap-4 border-b border-line-row py-3.5 last:border-b-0 last:pb-1"
              >
                <time className="w-14 shrink-0 font-mono text-[13px] font-medium text-ink-soft">
                  {fmtTime(event.start)}
                </time>
                <span className="min-w-0 flex-1 text-[14.5px] leading-snug">{event.title}</span>
                {event.demo ? (
                  <span className="shrink-0 font-mono text-[10.5px] tracking-[0.08em] text-faint">
                    DEMO
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* ── Commitments ───────────────────────────────────────────────────── */}
      <Card className="px-6 py-6 sm:px-8">
        <SectionLabel>Open commitments</SectionLabel>
        <p className="mt-1.5 text-[13px] text-muted">
          Swept by the Memory agent; approved from Memory Review or seeded — never
          auto-captured.
        </p>
        {data.commitments.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="Nothing open."
              hint="Run Commitment Sweep to find promises hiding in your notes."
            />
          </div>
        ) : (
          <ul className="mt-2">
            {data.commitments.map((commitment) => (
              <li
                key={commitment.id}
                className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-line-row py-3.5 last:border-b-0 last:pb-1"
              >
                <span className="min-w-0 flex-[1_1_220px] text-[14.5px] leading-snug">
                  {commitment.title}
                </span>
                <span className="shrink-0 font-mono text-[11.5px] uppercase tracking-[0.04em] text-muted-2">
                  {commitment.due_at
                    ? `due ${fmtDate(commitment.due_at)} · ${fmtTime(commitment.due_at)}`
                    : "no date"}
                </span>
                {commitment.source_ref ? (
                  <span className="min-w-0 max-w-full truncate font-mono text-[11px] text-faint">
                    {commitment.source_ref}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
