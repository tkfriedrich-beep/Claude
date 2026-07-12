"use client";

// Run detail: status, plan, live timeline, artifacts, sources, verification.
import { use } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ACTIVE_RUN_STATUSES, fmtTime, RUN_STATUS_STYLE, timeAgo } from "@/lib/utils";
import { ArtifactList } from "@/components/cockpit/artifact-list";
import { RunTimeline } from "@/components/cockpit/run-timeline";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Markdown } from "@/components/ui/markdown";
import { CardSkeleton, ErrorState } from "@/components/ui/states";
import Link from "next/link";
import { OctagonX, Pause, RotateCcw } from "lucide-react";

export default function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const { data: run, isLoading, error, refetch } = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.run(id),
    refetchInterval: (q) =>
      q.state.data && ACTIVE_RUN_STATUSES.includes(q.state.data.status) ? 2_000 : false,
  });

  const act = useMutation({
    mutationFn: (action: "cancel" | "interrupt" | "resume") =>
      action === "cancel" ? api.cancelRun(id) : action === "interrupt" ? api.interruptRun(id) : api.resumeRun(id),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["run", id] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  if (isLoading) return <div className="mx-auto max-w-3xl"><CardSkeleton lines={7} /></div>;
  if (error || !run) {
    return (
      <div className="mx-auto max-w-3xl">
        <ErrorState title="Run not found" detail={(error as Error)?.message} onRetry={() => refetch()} />
      </div>
    );
  }

  const style = RUN_STATUS_STYLE[run.status] ?? { label: run.status, tone: "muted" as const };
  const isActive = ACTIVE_RUN_STATUSES.includes(run.status);
  const result = run.result as {
    summary_md?: string;
    sources?: { label: string; reference: string }[];
    unresolved?: string[];
  } | null;
  const plan = run.plan as { steps?: string[]; assumption?: string | null } | null;
  const verification = run.verification as {
    passed?: boolean;
    checks?: { rule: string; passed: boolean; detail: string }[];
  } | null;

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-bold tracking-tight" data-testid="run-title">{run.title}</h1>
          <p className="mt-0.5 font-mono text-[11.5px] text-muted">
            {run.id} · {run.correlation_id ?? "no correlation id"} · started {timeAgo(run.created_at)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {run.shadow ? <Badge tone="outline">shadow</Badge> : null}
          <Badge tone={style.tone} data-testid="run-status">{style.label}</Badge>
        </div>
      </header>

      <div className="flex flex-wrap gap-2">
        {isActive ? (
          <>
            <Button size="sm" variant="warn" onClick={() => act.mutate("interrupt")}>
              <Pause className="size-3.5" /> Interrupt
            </Button>
            <Button size="sm" variant="danger" onClick={() => act.mutate("cancel")}>
              <OctagonX className="size-3.5" /> Cancel
            </Button>
          </>
        ) : null}
        {run.status === "interrupted" ? (
          <Button size="sm" variant="primary" onClick={() => act.mutate("resume")} data-testid="resume-btn">
            <RotateCcw className="size-3.5" /> Resume safely
          </Button>
        ) : null}
        {run.status === "awaiting_approval" ? (
          <Link href="/approvals"><Button size="sm" variant="warn">Review approval →</Button></Link>
        ) : null}
      </div>

      {run.status === "interrupted" ? (
        <Card className="border-warn/50">
          <CardBody className="pt-4 text-[13.5px]">
            {run.status_reason ?? "This run was interrupted."} Resuming replays completed steps
            from the audit log — external writes will not re-fire.
          </CardBody>
        </Card>
      ) : null}
      {run.error ? (
        <ErrorState title="Run failed" detail={run.error} />
      ) : null}

      {plan?.steps?.length ? (
        <Card>
          <CardHeader title="Plan" subtitle={plan.assumption ? `Assumption: ${plan.assumption}` : undefined} />
          <CardBody>
            <ol className="list-decimal space-y-1 pl-5 text-[13.5px]">
              {plan.steps.map((step, i) => <li key={i}>{step}</li>)}
            </ol>
          </CardBody>
        </Card>
      ) : null}

      {result?.summary_md ? (
        <Card>
          <CardHeader title="Result" />
          <CardBody data-testid="run-result">
            <Markdown content={result.summary_md} />
            {result.unresolved?.length ? (
              <div className="mt-3 rounded-[10px] border border-warn/40 bg-warn-soft/50 px-3.5 py-2.5">
                <p className="text-[12.5px] font-semibold text-warn">Unresolved</p>
                <ul className="mt-1 list-disc pl-5 text-[12.5px]">
                  {result.unresolved.map((item, i) => <li key={i}>{item}</li>)}
                </ul>
              </div>
            ) : null}
            {result.sources?.length ? (
              <div className="mt-3 flex flex-wrap gap-1.5" data-testid="source-chips">
                {result.sources.map((source, i) => (
                  <span key={i} title={source.reference}
                        className="rounded-full border border-line bg-raised px-2.5 py-1 font-mono text-[11px] text-muted">
                    {source.label}
                  </span>
                ))}
              </div>
            ) : null}
            <ArtifactList runId={run.id} />
          </CardBody>
        </Card>
      ) : null}

      {verification ? (
        <Card>
          <CardHeader
            title="Verification"
            action={
              <Badge tone={verification.passed ? "accent" : "danger"}>
                {verification.passed ? "passed" : "failed"}
              </Badge>
            }
          />
          <CardBody>
            <ul className="space-y-1 text-[13px]">
              {(verification.checks ?? []).map((check, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span aria-hidden className={check.passed ? "text-accent" : "text-danger"}>
                    {check.passed ? "✓" : "✗"}
                  </span>
                  <code className="font-mono text-[12px]">{check.rule}</code>
                  <span className="text-muted">— {check.detail}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title="Timeline"
          subtitle={`mode ${run.mode} · ${run.steps} tool calls · ${run.tokens_in + run.tokens_out} tokens · $${run.cost_usd.toFixed(3)}${run.finished_at ? ` · finished ${fmtTime(run.finished_at)}` : ""}`}
        />
        <CardBody>
          <RunTimeline runId={run.id} />
        </CardBody>
      </Card>
    </div>
  );
}
