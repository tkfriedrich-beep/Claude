"use client";

// Briefing (/, was Home) — answers "what matters today?" in one glance-line per zone.
// Column A: the briefing card (mono eyebrow · serif greeting · summary from real counts ·
// numbered what-matters) + today's calendar. Column B: active missions + agent roster.
// Column C: decisions awaiting judgment + active runs + suggested next.
// The composer, metrics and connector health moved to the global command band + ambient
// rail (relocated, not removed) — this page never duplicates them (OttoOS spec §04/§05).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Play } from "lucide-react";
import { api } from "@/lib/api";
import type { Briefing, ProjectItem } from "@/lib/types";
import { cn, fmtTime, greeting, RUN_STATUS_STYLE, timeAgo } from "@/lib/utils";
import { ApprovalCard } from "@/components/cockpit/approval-card";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { agentMetaFor, Monogram, type MonogramState } from "@/components/ui/monogram";
import {
  CardSkeleton,
  EmptyState,
  ErrorState,
  Kbd,
  SectionLabel,
} from "@/components/ui/states";

type BriefingRun = Briefing["active_runs"][number];
type BriefingSkill = Briefing["skills"][number];
type BriefingProject = Briefing["projects"][number];

// The summary sentence is composed ONLY from real counts — never invented copy.
function summaryLine(decisions: number, runs: number, missions: number): string {
  const d =
    decisions > 0
      ? `${decisions} decision${decisions === 1 ? "" : "s"} await${decisions === 1 ? "s" : ""} your judgment`
      : "No decisions are waiting";
  const r = runs > 0 ? `${runs} run${runs === 1 ? "" : "s"} in motion` : "nothing in motion";
  const m =
    missions > 0
      ? `${missions} mission${missions === 1 ? "" : "s"} on the board`
      : "no missions on the board";
  return `${d}, ${r}, and ${m}.`;
}

export default function BriefingPage() {
  const { data: briefing, isLoading, error, refetch } = useQuery({
    queryKey: ["briefing"],
    queryFn: api.briefing,
    refetchInterval: 30_000,
    retry: 1,
  });
  // Full approval objects for the canonical decision card — briefing.approvals.items is
  // only a summary (id/title/risk).
  const pendingQ = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => api.approvals("pending"),
    refetchInterval: 30_000,
  });
  // Mission paths/descriptions live on the projects endpoint; briefing carries the pulse.
  const { data: projectDetails } = useQuery({
    queryKey: ["projects"],
    queryFn: api.projects,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="flex flex-wrap items-start gap-7">
        <div className="min-w-0 flex-[1_1_520px] space-y-7">
          <CardSkeleton lines={5} />
          <CardSkeleton lines={3} />
        </div>
        <div className="min-w-0 flex-[1.35_1_600px] space-y-6">
          <CardSkeleton lines={3} />
          <CardSkeleton lines={6} />
        </div>
        <div className="min-w-0 flex-[1_1_480px] space-y-6">
          <CardSkeleton lines={4} />
          <CardSkeleton lines={3} />
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
  const pendingCount = briefing.approvals.pending;
  const pendingList = pendingQ.data ?? [];
  const projectById = new Map<string, ProjectItem>(
    (projectDetails ?? []).map((p) => [p.id, p]),
  );

  return (
    <div className="flex flex-wrap items-start gap-7">
      {/* ── Column A — the briefing itself ─────────────────────────────── */}
      <div className="fadeup flex min-w-0 max-w-[980px] flex-[1_1_520px] flex-col gap-7">
        <Card className="px-7 py-7 sm:px-9 sm:py-8">
          <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2">
            <span className="font-mono text-[11px] font-medium tracking-[2.5px] text-accent">
              {date.toLocaleDateString([], { weekday: "long" }).toUpperCase()} BRIEFING ·{" "}
              {date.toLocaleDateString([], { month: "long", day: "numeric" }).toUpperCase()}
            </span>
            {briefing.demo_mode ? (
              <span className="font-mono text-[10.5px] tracking-[0.08em] text-faint">
                DEMO DATA ACTIVE
              </span>
            ) : null}
            {briefing.kill_switch ? (
              <Badge tone="danger" className="ml-auto">
                <AlertTriangle className="size-3" /> Kill switch engaged
              </Badge>
            ) : null}
          </div>
          <h1
            className="otto-voice mt-4 text-[34px] font-medium leading-[1.15] text-ink sm:text-[38px]"
            data-testid="greeting"
          >
            {greeting(briefing.user_name, date)}.
          </h1>
          <p className="mt-2.5 text-[15.5px] leading-relaxed text-muted">
            {summaryLine(pendingCount, briefing.active_runs.length, briefing.projects.length)}
          </p>
          <div className="my-6 h-px bg-line-row" aria-hidden />
          <SectionLabel>What matters now</SectionLabel>
          {briefing.what_matters.length === 0 ? (
            <p className="otto-voice mt-3 text-[15px] text-muted">
              Nothing demands your attention.
            </p>
          ) : (
            <ol className="mt-1" data-testid="what-matters">
              {briefing.what_matters.map((item, i) => (
                <li key={i} className="border-b border-line-row last:border-b-0">
                  <Link
                    href={item.href}
                    className="flex items-baseline gap-4 rounded-[8px] px-1.5 py-3 hover:bg-accent-soft"
                  >
                    <span className="shrink-0 font-mono text-[12.5px] font-medium text-accent">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1 text-[14.5px] leading-snug">{item.text}</span>
                    <span
                      className={cn(
                        "shrink-0 font-mono text-[10.5px] uppercase tracking-[0.08em]",
                        item.kind === "approvals" ? "text-warn" : "text-faint",
                      )}
                    >
                      {item.kind}
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </Card>

        <Card className="px-7 py-6 sm:px-9">
          <div className="flex flex-wrap items-baseline gap-3">
            <SectionLabel>Today — calendar</SectionLabel>
            {briefing.agenda.demo ? <Badge tone="muted">demo data</Badge> : null}
            <Link
              href="/agenda"
              className="ml-auto font-mono text-[12px] text-accent hover:text-accent-hover"
            >
              FULL CALENDAR →
            </Link>
          </div>
          {briefing.agenda.events.length === 0 ? (
            <p className="otto-voice mt-4 text-[15px] text-muted">No events on the calendar.</p>
          ) : (
            <ul className="mt-2">
              {briefing.agenda.events.slice(0, 5).map((event) => (
                <li
                  key={event.id}
                  className="flex items-baseline gap-4 border-b border-line-row py-3 last:border-b-0"
                >
                  <time className="w-12 shrink-0 font-mono text-[12.5px] font-medium text-ink-soft">
                    {fmtTime(event.start)}
                  </time>
                  <span className="min-w-0 flex-1 truncate text-[14px]">{event.title}</span>
                  {event.demo ? (
                    <span className="shrink-0 font-mono text-[10.5px] text-faint">DEMO</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* ── Column B — missions + agent roster ─────────────────────────── */}
      <div className="fadeup flex min-w-0 flex-[1.35_1_600px] flex-col gap-6">
        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap items-baseline gap-3.5 px-1">
            <SectionLabel>Active missions</SectionLabel>
            <span className="text-[13px] text-muted">
              {briefing.projects.length} in motion
            </span>
            <Link
              href="/projects"
              className="ml-auto font-mono text-[12px] text-accent hover:text-accent-hover"
            >
              ALL MISSIONS →
            </Link>
          </div>
          {briefing.projects.length === 0 ? (
            <EmptyState
              title="No missions on the board."
              hint="No projects yet — point a vault at /projects."
            />
          ) : (
            briefing.projects.map((project) => (
              <MissionCard
                key={project.id}
                project={project}
                detail={projectById.get(project.id)}
              />
            ))
          )}
        </section>

        <Card className="px-6 py-6 sm:px-7">
          <div className="flex flex-wrap items-baseline gap-3.5">
            <SectionLabel>Agent roster</SectionLabel>
            <span className="text-[13px] text-muted">{briefing.skills.length} on staff</span>
            <Link
              href="/skills"
              className="ml-auto font-mono text-[12px] text-accent hover:text-accent-hover"
            >
              ALL AGENTS →
            </Link>
          </div>
          <div className="mt-5 grid gap-3.5 sm:grid-cols-2" data-testid="skill-grid">
            {briefing.skills.map((skill) => (
              <AgentTile key={skill.slug} skill={skill} runs={briefing.active_runs} />
            ))}
          </div>
        </Card>
      </div>

      {/* ── Column C — decisions, runs in motion, suggested next ───────── */}
      <div className="fadeup flex min-w-0 max-w-[860px] flex-[1_1_480px] flex-col gap-6">
        <section className="flex flex-col gap-3.5">
          <div className="flex items-baseline gap-3 px-1">
            <SectionLabel className={pendingCount > 0 ? "!text-warn" : undefined}>
              Decisions — your judgment
            </SectionLabel>
            <span
              className={cn(
                "ml-auto font-mono text-[11.5px]",
                pendingCount > 0 ? "text-warn" : "text-faint",
              )}
            >
              {pendingCount > 0 ? `${pendingCount} WAITING` : "CLEAR"}
            </span>
          </div>
          {pendingQ.isLoading ? (
            <CardSkeleton lines={4} />
          ) : pendingQ.error ? (
            <ErrorState
              title="Could not load the decision queue"
              detail={pendingQ.error.message}
              onRetry={() => pendingQ.refetch()}
            />
          ) : pendingList.length === 0 ? (
            <Card className="px-8 py-9 text-center">
              <p className="otto-voice text-[21px] text-accent-hover">The queue is clear.</p>
              <p className="mt-2 text-[13px] text-muted">
                Nothing waiting on you. Proposed actions with side effects will queue here.
              </p>
            </Card>
          ) : (
            pendingList
              .slice(0, 3)
              .map((approval) => <ApprovalCard key={approval.id} approval={approval} compact />)
          )}
          <Link
            href="/approvals"
            className="px-1 font-mono text-[12px] text-accent hover:text-accent-hover"
          >
            ALL DECISIONS{pendingList.length > 3 ? ` (${pendingList.length})` : ""} →
          </Link>
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex flex-wrap items-baseline gap-3 px-1">
            <SectionLabel>Active runs</SectionLabel>
            <span className="ml-auto text-[12px] text-muted">
              pause or cancel anything, any time
            </span>
          </div>
          {briefing.active_runs.length === 0 ? (
            <EmptyState
              title="Nothing running."
              hint="Runs appear here with live status the moment you launch one."
            />
          ) : (
            <ul className="space-y-2.5">
              {briefing.active_runs.map((run) => (
                <ActiveRunRow key={run.id} run={run} />
              ))}
            </ul>
          )}
        </section>

        <section className="flex flex-col gap-3">
          <div className="px-1">
            <SectionLabel>Suggested next</SectionLabel>
          </div>
          {briefing.suggestions.length === 0 ? (
            <p className="otto-voice px-1 text-[15px] text-muted">All caught up.</p>
          ) : (
            <div className="space-y-2.5">
              {briefing.suggestions.map((s) => (
                <SuggestionButton key={s.skill} suggestion={s} />
              ))}
            </div>
          )}
        </section>

        <p className="px-1 text-[12px] leading-relaxed text-faint">
          Nothing external runs without your approval. <Kbd>⌘K</Kbd> opens the palette.
        </p>
      </div>
    </div>
  );
}

function MissionCard({
  project,
  detail,
}: {
  project: BriefingProject;
  detail?: ProjectItem;
}) {
  return (
    <Link
      href="/projects"
      className="block rounded-[16px] border border-line-card bg-surface px-7 py-6 transition-colors hover:border-line-button"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="text-[17px] font-semibold tracking-[-0.01em]">{project.name}</span>
        <Badge tone={project.status === "active" ? "accent" : "muted"}>{project.status}</Badge>
        <span className="ml-auto font-mono text-[11px] text-muted-2">
          UPDATED {timeAgo(project.updated_at).toUpperCase()}
        </span>
      </div>
      {detail?.description ? (
        <p className="mt-1.5 line-clamp-1 text-[13.5px] text-muted">{detail.description}</p>
      ) : null}
      {detail?.path ? (
        <p className="mt-3 truncate font-mono text-[11.5px] text-faint">{detail.path}</p>
      ) : null}
    </Link>
  );
}

function AgentTile({ skill, runs }: { skill: BriefingSkill; runs: BriefingRun[] }) {
  const router = useRouter();
  const run = useMutation({
    mutationFn: () => api.runSkill(skill.slug),
    onSuccess: (r) => router.push(`/history/${r.id}`),
  });
  const meta = agentMetaFor(skill.slug, skill.name);
  const skillRuns = runs.filter((r) => r.skill_slug === skill.slug);
  const state: MonogramState = skillRuns.some((r) => r.status === "awaiting_approval")
    ? "needs"
    : skillRuns.length > 0
      ? "working"
      : "idle";
  const status =
    state === "needs"
      ? { dot: "bg-warn", text: "text-warn", label: "Needs your judgment" }
      : state === "working"
        ? { dot: "bg-accent", text: "text-accent-hover", label: "Working" }
        : { dot: "bg-faint", text: "text-muted-2", label: "Idle" };
  return (
    <div
      className={cn(
        "rounded-[12px] border p-4",
        state === "working" ? "border-(--accent-border) bg-accent-soft" : "border-line-control bg-tile",
      )}
    >
      <div className="flex items-center gap-2.5">
        <Monogram initials={meta.mono} state={state} />
        <div className="min-w-0 flex-1">
          <Link
            href={`/skills/${skill.slug}`}
            className="block truncate text-[14px] font-medium hover:text-accent-hover"
          >
            {meta.name}
          </Link>
          <span className="block truncate font-mono text-[10px] text-muted-2">{skill.slug}</span>
        </div>
        <Button
          size="sm"
          busy={run.isPending}
          onClick={() => run.mutate()}
          data-testid={`run-skill-${skill.slug}`}
          aria-label={`Run ${skill.name}`}
        >
          <Play className="size-3.5" /> Run
        </Button>
      </div>
      <p className="mt-2.5 line-clamp-2 text-[12px] leading-relaxed text-muted">
        {skill.description}
      </p>
      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2">
        <span className={cn("flex items-center gap-1.5 text-[12px]", status.text)}>
          <span aria-hidden className={cn("size-1.5 rounded-full", status.dot)} />
          {status.label}
        </span>
        <RiskBadge risk={skill.risk_level} />
      </div>
    </div>
  );
}

function ActiveRunRow({ run }: { run: BriefingRun }) {
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api.cancelRun(run.id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["briefing"] }),
  });
  const style = RUN_STATUS_STYLE[run.status] ?? { label: run.status, tone: "muted" as const };
  return (
    <li className="flex items-center justify-between gap-3 rounded-[11px] border border-line-card bg-surface px-4 py-3">
      <Link
        href={`/history/${run.id}`}
        className="min-w-0 truncate text-[13.5px] font-medium hover:text-accent-hover"
      >
        {run.title}
      </Link>
      <div className="flex shrink-0 items-center gap-2">
        <Badge tone={style.tone}>{style.label}</Badge>
        {run.status === "awaiting_approval" ? (
          <Link href="/approvals">
            <Button size="sm" variant="warn">
              Review
            </Button>
          </Link>
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
