"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtDate, fmtTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { Calendar } from "lucide-react";

export default function AgendaPage() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["agenda"], queryFn: api.agenda,
  });

  if (isLoading) return <div className="mx-auto max-w-3xl"><CardSkeleton lines={6} /></div>;
  if (error || !data) {
    return <div className="mx-auto max-w-3xl">
      <ErrorState detail={(error as Error)?.message} onRetry={() => refetch()} /></div>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <header>
        <h1 className="text-xl font-bold tracking-tight">Agenda</h1>
        <p className="text-[13px] text-muted">Today&apos;s events and your open commitments.</p>
      </header>

      <Card>
        <CardHeader title="Events"
                    action={data.events_demo ? <Badge tone="warn">demo data — connect Google for real events</Badge> : undefined} />
        <CardBody>
          {data.events.length === 0 ? (
            <EmptyState icon={<Calendar />} title="No events"
                        hint="Connect Google Workspace in Integrations to see your real calendar." />
          ) : (
            <ul className="space-y-2">
              {data.events.map((event) => (
                <li key={event.id} className="flex items-center gap-3 rounded-[10px] border border-line bg-raised px-3.5 py-2.5">
                  <time className="w-14 shrink-0 font-mono text-[12.5px] text-muted">{fmtTime(event.start)}</time>
                  <span className="text-[13.5px]">{event.title}</span>
                  {event.demo ? <Badge tone="outline" className="ml-auto">demo</Badge> : null}
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Open commitments" subtitle="Approved from Memory Review or seeded — never auto-captured." />
        <CardBody>
          {data.commitments.length === 0 ? (
            <p className="text-[13px] text-muted">
              Nothing open. Run Commitment Sweep to find promises hiding in your notes.
            </p>
          ) : (
            <ul className="space-y-2">
              {data.commitments.map((commitment) => (
                <li key={commitment.id} className="flex items-baseline justify-between gap-3 rounded-[10px] border border-line bg-raised px-3.5 py-2.5">
                  <span className="text-[13.5px]">{commitment.title}</span>
                  <span className="shrink-0 text-[12px] text-muted">
                    {commitment.due_at ? `due ${fmtDate(commitment.due_at)} ${fmtTime(commitment.due_at)}` : "no date"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
