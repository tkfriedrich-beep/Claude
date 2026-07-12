"use client";

// Home cockpit: greeting, pulse + composer, what-matters briefing, approvals,
// active run, suggestions, one-click skills, agenda (demo-labeled), project
// pulse, honest metrics, connector health (BUILD_BRIEF §Home screen).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Play, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { cn, fmtTime, greeting, RUN_STATUS_STYLE, timeAgo } from "@/lib/utils";
import { deriveOttoState, OttoPulse } from "@/components/cockpit/otto-pulse";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { CardSkeleton, EmptyState, ErrorState, Kbd } from "@/components/ui/states";
import { useState } from "react";

export default function HomePage() {
  const { data: briefing, isLoading, error, refetch } = useQuery({
    queryKey: ["briefing"],
    queryFn: api.briefing,
    refetchInterval: 30_000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-5xl space-y-4">
        <CardSkeleton lines={2} />
        <div className="grid gap-4 md:grid-cols-2">
          <CardSkeleton lines={4} />
          <CardSkeleton lines={4} />
        </div>
      </div>
    );
  }
  if (error || !briefing) {
    return (
      <div className="mx-auto max-w-3xl pt-10">
        <ErrorState
          title="The control plane is unreachable"
          detail={(error as Error)?.message}
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  const date = new Date(briefing.now);
  const ottoState = briefing.kill_switch
    ? "error"
    : deriveOttoState(briefing.active_runs, briefing.approvals.pending);

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      {/* header */}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-bold tracking-[-0.02em]" data-testid="greeting">
            {greeting(briefing.user_name, date)}
          </h1>
          <p className="text-[13px] text-muted">
            {date.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" })}
            {briefing.demo_mode ? " · demo data active" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {briefing.kill_switch ? (
            <Badge tone="danger">
              <AlertTriangle className="size-3" /> Kill switch engaged
            </Badge>
          ) : null}
          <SafeModePill on={briefing.safe_mode} />
        </div>
      </header>

      {/* pulse + composer */}
      <Card>
        <CardBody className="flex flex-col items-center gap-4 pt-5 sm:flex-row sm:items-center">
          <OttoPulse state={ottoState} size={88} />
          <div className="w-full flex-1">
            <HomeComposer assistantName={briefing.assistant_name} />
            <p className="mt-2 text-[12px] text-muted">
              Natural language, or pick a skill below. <Kbd>⌘K</Kbd> opens the palette.
              Nothing external runs without your approval.
            </p>
          </div>
        </CardBody>
      </Card>

      {/* what matters + approvals */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="What matters now" />
          <CardBody>
            <ul className="space-y-2" data-testid="what-matters">
              {briefing.what_matters.map((item, i) => (
                <li key={i}>
                  <Link
                    href={item.href}
                    className="group flex items-center justify-between gap-3 rounded-[10px] border border-line bg-raised px-3.5 py-2.5 text-[13.5px] hover:border-accent/40"
                  >
                    <span>{item.text}</span>
                    <ArrowRight className="size-4 shrink-0 text-muted group-hover:text-accent" />
                  </Link>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>

        <Card className={briefing.approvals.pending > 0 ? "border-warn/50" : undefined}>
          <CardHeader
            title="Approvals"
            action={
              briefing.approvals.pending > 0 ? (
                <Badge tone="warn">{briefing.approvals.pending} pending</Badge>
              ) : (
                <Badge tone="accent">clear</Badge>
              )
            }
          />
          <CardBody>
            {briefing.approvals.items.length === 0 ? (
              <p className="text-[13px] text-muted">
                Nothing waiting on you. Proposed actions with side effects will queue here.
              </p>
            ) : (
              <ul className="space-y-2">
                {briefing.approvals.items.map((item) => (
                  <li key={item.id} className="flex items-center justify-between gap-2 text-[13px]">
                    <span className="truncate">{item.title}</span>
                    <RiskBadge risk={item.risk_level} />
                  </li>
                ))}
              </ul>
            )}
            <Link href="/approvals" className="mt-3 inline-flex items-center gap-1 text-[13px] font-medium text-accent">
              Review queue <ArrowRight className="size-3.5" />
            </Link>
          </CardBody>
        </Card>
      </div>

      {/* active runs + suggestions */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Active runs" subtitle="Pause or cancel anything, any time" />
          <CardBody>
            {briefing.active_runs.length === 0 ? (
              <EmptyState
                title="Nothing running"
                hint="Runs appear here with live status the moment you launch one."
              />
            ) : (
              <ul className="space-y-2">
                {briefing.active_runs.map((run) => <ActiveRunRow key={run.id} run={run} />)}
              </ul>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Suggested next" />
          <CardBody className="space-y-2">
            {briefing.suggestions.length === 0 ? (
              <p className="text-[13px] text-muted">All caught up.</p>
            ) : (
              briefing.suggestions.map((s) => <SuggestionButton key={s.skill} suggestion={s} />)
            )}
          </CardBody>
        </Card>
      </div>

      {/* one-click skills */}
      <Card>
        <CardHeader
          title="Skills"
          action={<Link href="/skills" className="text-[13px] font-medium text-accent">All skills →</Link>}
        />
        <CardBody className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3" data-testid="skill-grid">
          {briefing.skills.slice(0, 6).map((skill) => (
            <SkillQuickCard key={skill.slug} skill={skill} />
          ))}
        </CardBody>
      </Card>

      {/* agenda + projects */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Today's agenda"
            action={briefing.agenda.demo ? <Badge tone="warn">demo data</Badge> : undefined}
          />
          <CardBody>
            {briefing.agenda.events.length === 0 ? (
              <p className="text-[13px] text-muted">No events.</p>
            ) : (
              <ul className="space-y-1.5">
                {briefing.agenda.events.slice(0, 5).map((event) => (
                  <li key={event.id} className="flex items-baseline gap-3 text-[13.5px]">
                    <time className="w-16 shrink-0 whitespace-nowrap font-mono text-[12px] text-muted">
                      {fmtTime(event.start)}
                    </time>
                    <span className="truncate">{event.title}</span>
                  </li>
                ))}
              </ul>
            )}
            <Link href="/agenda" className="mt-3 inline-block text-[13px] font-medium text-accent">
              Full agenda →
            </Link>
          </CardBody>
        </Card>
        <Card>
          <CardHeader
            title="Project pulse"
            action={<Link href="/projects" className="text-[13px] font-medium text-accent">Projects →</Link>}
          />
          <CardBody>
            {briefing.projects.length === 0 ? (
              <p className="text-[13px] text-muted">No projects yet — point a vault at /projects.</p>
            ) : (
              <ul className="space-y-1.5">
                {briefing.projects.map((project) => (
                  <li key={project.id} className="flex items-center justify-between gap-3 text-[13.5px]">
                    <span className="truncate">{project.name}</span>
                    <span className="shrink-0 text-[12px] text-muted">
                      {timeAgo(project.updated_at)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>

      {/* metrics + connector health */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="At a glance" subtitle="Real counts from your local activity" />
          <CardBody className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MetricTile label="Runs today" value={briefing.metrics.runs_today} />
            <MetricTile label="Approvals pending" value={briefing.metrics.approvals_pending}
                        tone={briefing.metrics.approvals_pending > 0 ? "warn" : undefined} />
            <MetricTile label="Artifacts this week" value={briefing.metrics.artifacts_week} />
            <MetricTile
              label="Connectors healthy"
              value={`${briefing.metrics.connectors_ok}/${briefing.metrics.connectors_total}`}
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="System health" />
          <CardBody>
            <ul className="space-y-1.5">
              {briefing.connector_health.slice(0, 7).map((c) => (
                <li key={c.slug} className="flex items-center justify-between text-[13px]">
                  <span className="truncate">{c.name}</span>
                  <HealthDot health={c.health} enabled={c.enabled} />
                </li>
              ))}
            </ul>
            <Link href="/integrations" className="mt-3 inline-block text-[13px] font-medium text-accent">
              Integrations →
            </Link>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function SafeModePill({ on }: { on: boolean }) {
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: () => api.patchSettings({ safe_mode: !on }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["briefing"] });
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });
  return (
    <button
      onClick={() => toggle.mutate()}
      data-testid="safe-mode-pill"
      className={cn(
        "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12.5px] font-medium",
        on ? "border-accent/40 bg-accent-soft text-accent" : "border-warn/50 bg-warn-soft text-warn",
      )}
      title={on ? "Safe Mode ON — external writes blocked. Click to turn off." : "Safe Mode OFF — external writes possible after approval. Click to turn on."}
    >
      <ShieldCheck className="size-3.5" />
      {on ? "Safe Mode on" : "Safe Mode off"}
    </button>
  );
}

function HomeComposer({ assistantName }: { assistantName: string }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const submit = useMutation({
    mutationFn: () => api.submitCommand({ text, mode: "draft" }),
    onSuccess: (run) => router.push(run.kind === "chat" ? `/command?session=${run.session_id ?? ""}&run=${run.id}` : `/history/${run.id}`),
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) submit.mutate();
      }}
      className="flex gap-2"
    >
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={`Ask ${assistantName}, or type “project pulse”…`}
        aria-label="Command input"
        data-testid="home-composer"
        className="h-11 w-full rounded-[12px] border border-line bg-raised px-4 text-[14.5px] placeholder:text-muted/70 focus-visible:border-accent"
      />
      <Button type="submit" variant="primary" size="lg" busy={submit.isPending} aria-label="Send command">
        <Play className="size-4" />
      </Button>
    </form>
  );
}

function ActiveRunRow({ run }: { run: { id: string; title: string; status: string } }) {
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api.cancelRun(run.id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["briefing"] }),
  });
  const style = RUN_STATUS_STYLE[run.status] ?? { label: run.status, tone: "muted" as const };
  return (
    <li className="flex items-center justify-between gap-3 rounded-[10px] border border-line bg-raised px-3.5 py-2.5">
      <Link href={`/history/${run.id}`} className="min-w-0 truncate text-[13.5px] font-medium hover:text-accent">
        {run.title}
      </Link>
      <div className="flex shrink-0 items-center gap-2">
        <Badge tone={style.tone}>{style.label}</Badge>
        {run.status === "awaiting_approval" ? (
          <Link href="/approvals"><Button size="sm" variant="warn">Review</Button></Link>
        ) : (
          <Button size="sm" variant="ghost" busy={cancel.isPending} onClick={() => cancel.mutate()}>
            Cancel
          </Button>
        )}
      </div>
    </li>
  );
}

function SuggestionButton({ suggestion }: { suggestion: { skill: string; label: string } }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const run = useMutation({
    mutationFn: () => api.runSkill(suggestion.skill),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ["briefing"] });
      router.push(`/history/${r.id}`);
    },
  });
  return (
    <Button className="w-full justify-between" busy={run.isPending} onClick={() => run.mutate()}>
      {suggestion.label}
      <ArrowRight className="size-4" />
    </Button>
  );
}

function SkillQuickCard({
  skill,
}: {
  skill: { slug: string; name: string; description: string; risk_level: string };
}) {
  const router = useRouter();
  const run = useMutation({
    mutationFn: () => api.runSkill(skill.slug),
    onSuccess: (r) => router.push(`/history/${r.id}`),
  });
  return (
    <div className="group flex flex-col rounded-[12px] border border-line bg-raised p-3.5 hover:border-accent/40">
      <div className="flex items-start justify-between gap-2">
        <Link href={`/skills/${skill.slug}`} className="text-[13.5px] font-semibold hover:text-accent">
          {skill.name}
        </Link>
        <RiskBadge risk={skill.risk_level} />
      </div>
      <p className="mt-1 line-clamp-2 flex-1 text-[12.5px] text-muted">{skill.description}</p>
      <Button size="sm" className="mt-2.5 self-start" busy={run.isPending}
              onClick={() => run.mutate()} data-testid={`run-skill-${skill.slug}`}>
        <Play className="size-3.5" /> Run
      </Button>
    </div>
  );
}

function MetricTile({ label, value, tone }: { label: string; value: number | string; tone?: "warn" }) {
  return (
    <div className="rounded-[12px] border border-line bg-raised px-3.5 py-3">
      <p className={cn("text-xl font-bold tabular-nums tracking-tight", tone === "warn" && "text-warn")}>{value}</p>
      <p className="text-[12px] text-muted">{label}</p>
    </div>
  );
}

function HealthDot({ health, enabled }: { health: string; enabled: boolean }) {
  const label = !enabled ? "disabled" : health;
  const color = !enabled
    ? "bg-line"
    : health === "ok"
      ? "bg-accent"
      : health === "mock"
        ? "bg-warn"
        : health === "degraded"
          ? "bg-warn"
          : health === "unavailable"
            ? "bg-danger"
            : "bg-line";
  return (
    <span className="flex items-center gap-1.5 text-[12px] text-muted">
      <span aria-hidden className={cn("size-2 rounded-full", color)} />
      {label}
    </span>
  );
}
