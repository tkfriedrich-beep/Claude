"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtDate, fmtTime, RUN_STATUS_STYLE } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { SegmentedControl } from "@/components/ui/segmented";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { Clock } from "lucide-react";

// Filter values double as the /runs?status= list the control plane expects.
const FILTERS = [
  { value: "", label: "ALL" },
  { value: "completed", label: "COMPLETED" },
  { value: "failed,cancelled,interrupted", label: "ATTENTION" },
  {
    value: "awaiting_approval,executing,queued,triaging,planning,verifying,reviewing",
    label: "ACTIVE",
  },
];

export default function HistoryPage() {
  const [filter, setFilter] = useState("");
  const { data: runs, isLoading, error, refetch } = useQuery({
    queryKey: ["runs", "history", filter],
    queryFn: () => api.runs({ status: filter || undefined, limit: 100 }),
    refetchInterval: 15_000,
  });

  return (
    <div className="mx-auto max-w-[1460px] space-y-[22px]">
      <header>
        <h1 className="text-[26px] font-semibold tracking-[-0.3px]">Archive</h1>
        <p className="mt-1 text-[14px] text-muted">
          Every run — commands and agents — with a replayable, human-readable timeline.
          Survives restarts.
        </p>
      </header>

      <SegmentedControl options={FILTERS} value={filter} onChange={setFilter} mono
                        label="Run filter" />

      {isLoading ? (
        <CardSkeleton lines={6} />
      ) : error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : (runs ?? []).length === 0 ? (
        <EmptyState icon={<Clock />} title="Nothing in the archive yet."
                    hint="Run an agent or send a command — every execution is recorded here." />
      ) : (
        <ul className="fadeup divide-y divide-line-row overflow-hidden rounded-[16px] border border-line-card bg-surface"
            data-testid="history-list">
          {(runs ?? []).map((run) => {
            const style = RUN_STATUS_STYLE[run.status] ?? { label: run.status, tone: "muted" as const };
            const duration = run.started_at && run.finished_at
              ? `${Math.max(1, Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000))}s`
              : null;
            return (
              <li key={run.id}>
                <Link href={`/history/${run.id}`}
                      className="group flex items-center gap-[18px] px-[30px] py-[17px]">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[15px] font-medium leading-snug transition-colors group-hover:text-accent-hover">
                      {run.title}
                    </p>
                    <p className="mt-1 truncate font-mono text-[11.5px] text-faint">
                      {run.kind === "skill" ? run.skill_slug : `command · ${run.provider ?? "—"}`}
                      {" · "}{fmtDate(run.created_at)} {fmtTime(run.created_at)}
                      {duration ? ` · ${duration}` : ""}
                      {run.steps ? ` · ${run.steps} tool calls` : ""}
                      {run.cost_usd > 0 ? ` · $${run.cost_usd.toFixed(3)}` : ""}
                    </p>
                  </div>
                  {run.shadow ? <Badge tone="outline">shadow</Badge> : null}
                  <Badge tone={style.tone}>{style.label}</Badge>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
