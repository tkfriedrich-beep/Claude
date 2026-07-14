"use client";

// Command (OttoOS): persistent conversation surface — start/resume/interrupt/cancel,
// streamed replies, plan + tool timeline, artifacts and source chips. Carries the
// band handoff contract: ?prefill / ?mode / ?autosubmit=1 (submit once) / ?preview=1.
import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Run } from "@/lib/types";
import { ACTIVE_RUN_STATUSES, cn, RUN_STATUS_STYLE, timeAgo } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Markdown } from "@/components/ui/markdown";
import { Input, Select } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented";
import { CardSkeleton, EmptyState, ErrorState, Kbd, SectionLabel, Skeleton } from "@/components/ui/states";
import { RunTimeline } from "@/components/cockpit/run-timeline";
import { ArtifactList } from "@/components/cockpit/artifact-list";
import { OctagonX, Pause, Play, RotateCcw } from "lucide-react";

// Execution modes map 1:1 to the API's run modes (spec §03). There is deliberately no
// per-command "allowlist"/"in-policy" toggle: whether an allow-listed tool runs without
// approval is a property of the agent's persisted autonomy (level 5) plus Settings →
// Policies — a mode label must never silently raise effective autonomy.
const AUTONOMY = [
  { value: "read_only", label: "Advise" },
  { value: "draft", label: "Draft" },
  { value: "act", label: "Execute" },
] as const;
type CommandMode = "read_only" | "draft" | "act";
type Autonomy = CommandMode;

const RISK_ORDER = ["R0", "R1", "R2", "R3", "R4"];

// The planner emits plain string steps today; tolerate structured steps with a
// per-step risk if a future plan provides them. Never invent one.
type PlanStep = string | { text?: string; step?: string; risk?: string };
interface RunPlan {
  steps?: PlanStep[];
  assumption?: string | null;
  side_effects_expected?: boolean;
  expected_tools?: string[];
}
interface RunResult {
  summary_md?: string;
  sources?: { label: string; reference: string }[];
}

export default function CommandPage() {
  return (
    <Suspense fallback={<CardSkeleton lines={6} />}>
      <CommandInner />
    </Suspense>
  );
}

function CommandInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const sessionId = searchParams.get("session");
  const [text, setText] = useState("");
  const [autonomy, setAutonomy] = useState<Autonomy>("draft");
  const [skillSlug, setSkillSlug] = useState("");
  const [domainKey, setDomainKey] = useState("");
  const [budget, setBudget] = useState("");
  const [contextPackId, setContextPackId] = useState("");
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const consumedHandoff = useRef<string | null>(null);

  const { data: sessions, isLoading: sessionsLoading, error: sessionsError } = useQuery({
    queryKey: ["sessions"],
    queryFn: api.sessions,
  });
  const { data: skills } = useQuery({ queryKey: ["skills"], queryFn: api.skills });
  const { data: domains } = useQuery({ queryKey: ["domains"], queryFn: api.domains });
  const {
    data: runs,
    isLoading: runsLoading,
    error: runsError,
    refetch: refetchRuns,
  } = useQuery({
    queryKey: ["session-runs", sessionId],
    queryFn: () => (sessionId ? api.sessionRuns(sessionId) : Promise.resolve([] as Run[])),
    enabled: Boolean(sessionId),
    refetchInterval: 2_000, // deltas persist as events; poll keeps replies snappy alongside SSE
  });

  const submit = useMutation({
    // Explicit variables so the band's autosubmit never races React state.
    mutationFn: (vars: { text: string; mode: CommandMode }) => {
      const budgetUsd = budget.trim() === "" ? undefined : Number(budget);
      return api.submitCommand({
        text: vars.text,
        mode: vars.mode,
        session_id: sessionId ?? undefined,
        skill_slug: skillSlug || undefined,
        domain_key: domainKey || undefined,
        context_pack_id: contextPackId.trim() || undefined,
        budget_usd: budgetUsd !== undefined && Number.isFinite(budgetUsd) ? budgetUsd : undefined,
      });
    },
    onSuccess: async (run) => {
      setText("");
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      if (run.kind !== "chat") {
        router.push(`/history/${run.id}`);
        return;
      }
      if (sessionId) {
        queryClient.invalidateQueries({ queryKey: ["session-runs", sessionId] });
        return;
      }
      // the session id materializes when the worker claims the run — poll briefly
      for (let attempt = 0; attempt < 20; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        try {
          const detail = await api.run(run.id);
          if (detail.session_id) {
            router.replace(`/command?session=${detail.session_id}`);
            queryClient.invalidateQueries({ queryKey: ["sessions"] });
            return;
          }
        } catch {
          /* transient — retry */
        }
      }
    },
  });
  const submitMutate = submit.mutate;

  // Band handoff: consume ?prefill/?mode/?autosubmit/?preview exactly once per
  // navigation (ref guard survives StrictMode double-effects), then strip the
  // params so a reload can never re-submit.
  useEffect(() => {
    const hasHandoff =
      searchParams.has("prefill") ||
      searchParams.has("mode") ||
      searchParams.has("autosubmit") ||
      searchParams.has("preview");
    if (!hasHandoff) {
      consumedHandoff.current = null; // ready for the next band handoff
      return;
    }
    const key = searchParams.toString();
    if (consumedHandoff.current === key) return;
    consumedHandoff.current = key;

    const prefill = (searchParams.get("prefill") ?? "").trim();
    const modeParam = searchParams.get("mode");
    const validMode =
      modeParam === "read_only" || modeParam === "draft" || modeParam === "act"
        ? modeParam
        : null;
    if (validMode) setAutonomy(validMode);
    if (prefill) setText(prefill);
    if (searchParams.get("autosubmit") === "1" && prefill) {
      submitMutate({ text: prefill, mode: validMode ?? autonomy });
    } else {
      // preview=1 (or bare prefill): hand the cursor to the composer, caret at end
      requestAnimationFrame(() => {
        const el = composerRef.current;
        if (el) {
          el.focus();
          el.setSelectionRange(el.value.length, el.value.length);
        }
      });
    }
    router.replace(sessionId ? `/command?session=${sessionId}` : "/command", { scroll: false });
  }, [searchParams, router, sessionId, submitMutate, autonomy]);

  const sendCurrent = () => {
    if (text.trim()) submitMutate({ text, mode: autonomy });
  };

  return (
    <div className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[236px_minmax(0,1fr)]">
      {/* session list */}
      <aside className="hidden lg:block">
        <Card>
          <CardHeader title="Sessions" />
          <CardBody className="space-y-1">
            <button
              onClick={() => router.push("/command")}
              className={cn(
                "w-full rounded-[9px] px-2.5 py-2 text-left text-[13px] font-medium",
                !sessionId
                  ? "bg-accent-soft text-accent-hover"
                  : "text-muted-2 hover:bg-tile hover:text-ink",
              )}
            >
              + New session
            </button>
            {sessionsLoading ? (
              <div className="space-y-2 px-2.5 py-2" role="status" aria-label="Loading sessions">
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-4/5" />
                <Skeleton className="h-3 w-3/5" />
              </div>
            ) : sessionsError ? (
              <p role="alert" className="px-2.5 py-2 text-[12px] text-danger">
                {(sessionsError as Error).message}
              </p>
            ) : (
              (sessions ?? []).map((session) => (
                <button
                  key={session.id}
                  onClick={() => router.push(`/command?session=${session.id}`)}
                  className={cn(
                    "w-full truncate rounded-[9px] px-2.5 py-2 text-left text-[13px]",
                    sessionId === session.id
                      ? "bg-accent-soft text-accent-hover"
                      : "text-muted-2 hover:bg-tile hover:text-ink",
                  )}
                  title={session.title}
                >
                  {session.title}
                  <span className="block font-mono text-[10.5px] tracking-[0.04em] opacity-70">
                    {session.provider} · {timeAgo(session.last_active_at)}
                  </span>
                </button>
              ))
            )}
          </CardBody>
        </Card>
      </aside>

      {/* conversation + composer */}
      <div className="flex min-h-[70dvh] flex-col gap-4">
        <header>
          <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Command</h1>
          <p className="mt-1 text-[14px] text-muted-2">
            Natural language in, governed execution out. Consequential work shows its plan, and
            external writes pause for your approval — unless you&apos;ve allow-listed a tool in
            Settings → Policies.
          </p>
        </header>

        <div className="flex-1 space-y-4">
          {!sessionId ? (
            <EmptyState
              title="Start a conversation."
              hint="Chat turns and agent runs share the same audit trail — everything lands in the Archive with a replayable timeline."
            />
          ) : runsError ? (
            <ErrorState
              title="Couldn't load this session"
              detail={(runsError as Error).message}
              onRetry={() => refetchRuns()}
            />
          ) : runsLoading ? (
            <CardSkeleton lines={4} />
          ) : (runs ?? []).length === 0 ? (
            <EmptyState title="A quiet thread." hint="Send the first command below." />
          ) : (
            (runs ?? []).map((run) => (
              <ConversationTurn
                key={run.id}
                run={run}
                expanded={expandedRun === run.id}
                onToggle={() => setExpandedRun(expandedRun === run.id ? null : run.id)}
              />
            ))
          )}
        </div>

        {/* XL composer */}
        <Card className="sticky bottom-16 z-10 lg:bottom-4">
          <CardBody className="space-y-3 pt-4">
            <div className="flex flex-wrap items-end gap-3 rounded-[12px] border border-line-control bg-raised p-2.5 pl-4 focus-within:border-(--accent-border)">
              <textarea
                ref={composerRef}
                rows={2}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendCurrent();
                  }
                }}
                placeholder="Direct the system, define an objective, or ask a question…"
                aria-label="Message"
                data-testid="command-composer"
                className="min-h-[52px] w-full min-w-[200px] flex-1 resize-none bg-transparent py-1 text-[15.5px] leading-relaxed text-ink outline-none placeholder:text-muted/70"
              />
              <Button
                variant="primary"
                busy={submit.isPending}
                disabled={!text.trim()}
                onClick={sendCurrent}
                data-testid="command-send"
              >
                <Play className="size-4" /> Execute
              </Button>
            </div>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <div data-testid="mode-select" className="flex items-center gap-2.5">
                <SectionLabel>Mode</SectionLabel>
                <SegmentedControl
                  options={AUTONOMY.map((a) => ({ value: a.value, label: a.label }))}
                  value={autonomy}
                  onChange={setAutonomy}
                  size="sm"
                  label="Execution mode"
                />
              </div>
              <Select value={skillSlug} onChange={(e) => setSkillSlug(e.target.value)} aria-label="Skill">
                <option value="">No agent — free chat</option>
                {(skills ?? []).map((skill) => (
                  <option key={skill.slug} value={skill.slug}>{skill.name}</option>
                ))}
              </Select>
              <Select value={domainKey} onChange={(e) => setDomainKey(e.target.value)} aria-label="Domain">
                <option value="">Domain — auto</option>
                {(domains ?? []).map((domain) => (
                  <option key={domain.key} value={domain.key} disabled={!domain.enabled}>
                    {domain.name}
                    {domain.enabled ? "" : " (disabled)"}
                  </option>
                ))}
              </Select>
              <div className="w-28">
                <Input
                  type="number"
                  min={0}
                  step={0.25}
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                  aria-label="Budget per run (USD)"
                  placeholder="$ / run"
                />
              </div>
              <div className="w-40">
                <Input
                  value={contextPackId}
                  onChange={(e) => setContextPackId(e.target.value)}
                  aria-label="Context pack"
                  placeholder="context pack id"
                  className="font-mono"
                />
              </div>
              <p className="ml-auto hidden text-[11.5px] text-faint md:block">
                No slash commands needed — every control is explicit here. <Kbd>Enter</Kbd> send ·{" "}
                <Kbd>Shift+Enter</Kbd> newline
              </p>
            </div>

            {submit.isError ? (
              <p role="alert" className="text-[12.5px] text-danger">
                {(submit.error as Error).message}
              </p>
            ) : null}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function ConversationTurn({
  run,
  expanded,
  onToggle,
}: {
  run: Run;
  expanded: boolean;
  onToggle: () => void;
}) {
  const queryClient = useQueryClient();
  const [planDismissed, setPlanDismissed] = useState(false);
  const style = RUN_STATUS_STYLE[run.status] ?? { label: run.status, tone: "muted" as const };
  const result = run.result as RunResult | null;
  const plan = run.plan as RunPlan | null;
  const reply = result?.summary_md;
  const isActive = ACTIVE_RUN_STATUSES.includes(run.status);

  // Consequential work shows its plan; a single-step read-only chat plan stays quiet.
  const steps = plan?.steps ?? [];
  const showPlan =
    steps.length > 0 &&
    !planDismissed &&
    (steps.length > 1 || plan?.side_effects_expected === true || run.status === "awaiting_approval");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["session-runs"] });

  return (
    <div className="fadeup space-y-2">
      {run.command_text ? (
        <div className="ml-auto w-fit max-w-[85%] rounded-[14px] rounded-br-[4px] border border-line-control bg-raised px-4 py-2.5 text-[14px] text-ink">
          {run.command_text}
        </div>
      ) : null}
      <Card>
        <CardBody className="pt-4">
          <div className="mb-2 flex flex-wrap items-center gap-2.5">
            <Badge tone={style.tone}>{style.label}</Badge>
            <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-faint">
              {run.skill_slug ?? "chat"} · {run.mode} · {timeAgo(run.created_at)}
            </span>
            <div className="ml-auto flex flex-wrap items-center gap-1.5">
              {isActive ? (
                <>
                  <Button
                    size="sm"
                    variant="warn"
                    title="State preserved — resuming replays the audit log; external writes never re-fire"
                    onClick={() => api.interruptRun(run.id).then(invalidate)}
                  >
                    <Pause className="size-3.5" /> Interrupt
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => api.cancelRun(run.id).then(invalidate)}>
                    <OctagonX className="size-3.5" /> Cancel
                  </Button>
                </>
              ) : null}
              {run.status === "interrupted" ? (
                <Button size="sm" variant="ghost" onClick={() => api.resumeRun(run.id).then(invalidate)}>
                  <RotateCcw className="size-3.5" /> Resume
                </Button>
              ) : null}
              <button
                onClick={onToggle}
                aria-expanded={expanded}
                className="ml-1 font-mono text-[10.5px] tracking-[0.12em] text-muted hover:text-ink"
              >
                {expanded ? "HIDE TIMELINE" : "TIMELINE"}
              </button>
            </div>
          </div>

          {showPlan && plan ? (
            <PlanCard run={run} plan={plan} steps={steps} onDismiss={() => setPlanDismissed(true)} />
          ) : null}

          {reply ? (
            <div
              data-testid="assistant-reply"
              className="otto-voice text-[16.5px] leading-[1.65] text-ink-soft [&_li]:text-[15px] [&_p]:my-2 [&_p]:text-[16.5px] [&_p]:leading-[1.65]"
            >
              <Markdown content={reply} />
            </div>
          ) : isActive ? (
            <p className="stream-caret text-[14px] text-muted">Working</p>
          ) : run.error ? (
            <p className="text-[13.5px] text-danger">{run.error}</p>
          ) : (
            <p className="text-[13.5px] text-muted">{run.status_reason ?? "No reply."}</p>
          )}

          {result?.sources?.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5" data-testid="source-chips">
              {result.sources.map((source, i) => (
                <span
                  key={i}
                  title={source.reference}
                  className="rounded-full border border-line-control bg-raised px-2.5 py-1 font-mono text-[10.5px] text-muted"
                >
                  {source.label}
                </span>
              ))}
            </div>
          ) : null}
          {run.mode === "read_only" && !isActive ? (
            <p className="mt-3 font-mono text-[10.5px] tracking-[0.08em] text-faint">
              ADVISORY ONLY — NOTHING WAS EXECUTED.
            </p>
          ) : null}

          {expanded ? (
            <div className="mt-4 space-y-3 border-t border-line-row pt-4">
              <RunTimeline runId={run.id} />
              <details>
                <summary className="cursor-pointer font-mono text-[11.5px] text-muted-2 hover:text-ink">
                  Technical details — run record (JSON)
                </summary>
                <pre className="mt-2 max-h-64 overflow-auto rounded-[10px] border border-line-row bg-well p-3.5 font-mono text-[11px] leading-[1.7] text-muted">
                  {JSON.stringify(
                    {
                      id: run.id,
                      kind: run.kind,
                      mode: run.mode,
                      provider: run.provider,
                      status: run.status,
                      status_reason: run.status_reason,
                      cost_usd: run.cost_usd,
                      tokens_in: run.tokens_in,
                      tokens_out: run.tokens_out,
                      steps: run.steps,
                      correlation_id: run.correlation_id,
                      plan: run.plan,
                      result: run.result,
                      error: run.error,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              <ArtifactList runId={run.id} />
            </div>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}

function PlanCard({
  run,
  plan,
  steps,
  onDismiss,
}: {
  run: Run;
  plan: RunPlan;
  steps: PlanStep[];
  onDismiss: () => void;
}) {
  const risks = steps
    .map((step) => (typeof step === "string" ? null : (step.risk ?? null)))
    .filter((risk): risk is string => Boolean(risk));
  const highest = risks.length
    ? risks.reduce((a, b) => (RISK_ORDER.indexOf(b) > RISK_ORDER.indexOf(a) ? b : a))
    : null;
  const callout = highest
    ? `HIGHEST STEP ${highest} — ${plan.side_effects_expected ? "PAUSES FOR APPROVAL" : "NO SIDE EFFECTS"}`
    : plan.side_effects_expected
      ? "SIDE EFFECTS EXPECTED — PAUSES FOR APPROVAL"
      : "READS ONLY — NO SIDE EFFECTS";

  return (
    <div className="mb-4 rounded-[12px] border border-(--accent-border) bg-tile px-4 py-3.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-[10.5px] font-medium tracking-[0.18em] text-accent-hover">
          PLAN
        </span>
        <span className="ml-auto font-mono text-[10.5px] tracking-[0.06em] text-muted-2">{callout}</span>
      </div>
      <ol className="mt-2">
        {steps.map((step, i) => {
          const stepText = typeof step === "string" ? step : (step.text ?? step.step ?? "—");
          const stepRisk = typeof step === "string" ? null : (step.risk ?? null);
          return (
            <li
              key={i}
              className="flex items-baseline gap-3.5 border-b border-line-row py-2 text-[13.5px] last:border-b-0"
            >
              <span className="font-mono text-[11.5px] font-medium text-accent-hover">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="flex-1">{stepText}</span>
              {stepRisk ? <span className="font-mono text-[10.5px] text-faint">{stepRisk}</span> : null}
            </li>
          );
        })}
      </ol>
      {plan.assumption ? (
        <p className="mt-2 text-[12.5px] text-muted">Assumption — {plan.assumption}</p>
      ) : null}
      {plan.expected_tools?.length ? (
        <p className="mt-1.5 font-mono text-[10.5px] tracking-[0.04em] text-faint">
          TOOLS · {plan.expected_tools.join(" · ")}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2.5">
        {run.status === "awaiting_approval" ? (
          <Link href="/approvals">
            <Button size="sm" variant="warn" title="Opens Decisions — the approval is recorded there">
              Confirm &amp; run →
            </Button>
          </Link>
        ) : null}
        <Button size="sm" variant="ghost" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}
