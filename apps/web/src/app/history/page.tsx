"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn, fmtDate, fmtTime, RUN_STATUS_STYLE } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { Clock } from "lucide-react";

const FILTERS = [
  { key: "", label: "All" },
  { key: "completed", label: "Completed" },
  { key: "awaiting_approval,executing,queued,triaging,planning,verifying,reviewing", label: "Active" },
  { key: "failed,cancelled,interrupted", label: "Attention" },
];

export default function HistoryPage() {
  const [filter, setFilter] = useState("");
  const { data: runs, isLoading, error, refetch } = useQuery({
    queryKey: ["runs", "history", filter],
    queryFn: () => api.runs({ status: filter || undefined, limit: 100 }),
    refetchInterval: 15_000,
  });

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <header>
        <h1 className="text-xl font-bold tracking-tight">History</h1>
        <p className="text-[13px] text-muted">
          Every run — chat turns and skills — with a replayable, human-readable timeline.
          Survives restarts.
        </p>
      </header>

      <div role="tablist" aria-label="Run filter" className="flex flex-wrap gap-1 rounded-[12px] border border-line bg-surface p-1 w-fit">
        {FILTERS.map(({ key, label }) => (
          <button key={key} role="tab" aria-selected={filter === key} onClick={() => setFilter(key)}
                  className={cn("rounded-[9px] px-3.5 py-1.5 text-[13px] font-medium",
                    filter === key ? "bg-accent text-white" : "text-muted hover:text-ink")}>
            {label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <CardSkeleton lines={6} />
      ) : error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : (runs ?? []).length === 0 ? (
        <EmptyState icon={<Clock />} title="No runs yet"
                    hint="Run a skill or send a command — every execution is recorded here." />
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-[14px] border border-line bg-surface"
            data-testid="history-list">
          {(runs ?? []).map((run) => {
            const style = RUN_STATUS_STYLE[run.status] ?? { label: run.status, tone: "muted" as const };
            const duration = run.started_at && run.finished_at
              ? `${Math.max(1, Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000))}s`
              : null;
            return (
              <li key={run.id}>
                <Link href={`/history/${run.id}`}
                      className="flex items-center gap-3 px-4 py-3 hover:bg-line/20">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[14px] font-medium">{run.title}</p>
                    <p className="text-[12px] text-muted">
                      {run.kind === "skill" ? run.skill_slug : `chat · ${run.provider ?? "—"}`}
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
