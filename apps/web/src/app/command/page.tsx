"use client";

// Command: persistent conversation surface — start/resume/interrupt/cancel,
// streamed replies, plan + tool timeline, artifacts and source chips.
import { Suspense, useMemo, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Run } from "@/lib/types";
import { ACTIVE_RUN_STATUSES, cn, RUN_STATUS_STYLE, timeAgo } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Markdown } from "@/components/ui/markdown";
import { Select, Textarea } from "@/components/ui/input";
import { CardSkeleton, EmptyState } from "@/components/ui/states";
import { RunTimeline } from "@/components/cockpit/run-timeline";
import { ArtifactList } from "@/components/cockpit/artifact-list";
import { OctagonX, Pause, Play, RotateCcw } from "lucide-react";

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
  const [mode, setMode] = useState<"read_only" | "draft" | "act">("draft");
  const [skillSlug, setSkillSlug] = useState("");
  const [expandedRun, setExpandedRun] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const { data: sessions } = useQuery({ queryKey: ["sessions"], queryFn: api.sessions });
  const { data: skills } = useQuery({ queryKey: ["skills"], queryFn: api.skills });
  const { data: runs, isLoading: runsLoading } = useQuery({
    queryKey: ["session-runs", sessionId],
    queryFn: () => (sessionId ? api.sessionRuns(sessionId) : Promise.resolve([] as Run[])),
    enabled: Boolean(sessionId),
    refetchInterval: 2_000, // deltas persist as events; poll keeps replies snappy alongside SSE
  });

  const submit = useMutation({
    mutationFn: () =>
      api.submitCommand({
        text,
        mode,
        session_id: sessionId ?? undefined,
        skill_slug: skillSlug || undefined,
      }),
    onSuccess: (run) => {
      setText("");
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      if (run.kind === "chat") {
        // session id materializes once the worker picks the run up
        setTimeout(async () => {
          const detail = await api.run(run.id);
          if (detail.session_id) router.replace(`/command?session=${detail.session_id}`);
          queryClient.invalidateQueries({ queryKey: ["session-runs"] });
          queryClient.invalidateQueries({ queryKey: ["sessions"] });
        }, 700);
      } else {
        router.push(`/history/${run.id}`);
      }
    },
  });

  const activeRun = useMemo(
    () => (runs ?? []).find((r) => ACTIVE_RUN_STATUSES.includes(r.status)),
    [runs],
  );

  return (
    <div className="mx-auto grid max-w-6xl gap-5 lg:grid-cols-[240px_minmax(0,1fr)]">
      {/* session list */}
      <aside className="hidden lg:block">
        <Card>
          <CardHeader title="Sessions" />
          <CardBody className="space-y-1">
            <button
              onClick={() => router.push("/command")}
              className={cn(
                "w-full rounded-[10px] px-2.5 py-2 text-left text-[13px] font-medium",
                !sessionId ? "bg-accent-soft text-accent" : "hover:bg-line/40",
              )}
            >
              + New session
            </button>
            {(sessions ?? []).map((session) => (
              <button
                key={session.id}
                onClick={() => router.push(`/command?session=${session.id}`)}
                className={cn(
                  "w-full truncate rounded-[10px] px-2.5 py-2 text-left text-[13px]",
                  sessionId === session.id ? "bg-accent-soft text-accent" : "text-muted hover:bg-line/40",
                )}
                title={session.title}
              >
                {session.title}
                <span className="block text-[11px] opacity-70">
                  {session.provider} · {timeAgo(session.last_active_at)}
                </span>
              </button>
            ))}
          </CardBody>
        </Card>
      </aside>

      {/* conversation + composer */}
      <div className="flex min-h-[70dvh] flex-col gap-4">
        <div ref={listRef} className="flex-1 space-y-4">
          {!sessionId ? (
            <EmptyState
              title="Start a conversation"
              hint="Chat turns and skill runs share the same audit trail — everything lands in History with a replayable timeline."
            />
          ) : runsLoading ? (
            <CardSkeleton lines={4} />
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

        {/* composer */}
        <Card className="sticky bottom-16 lg:bottom-4">
          <CardBody className="space-y-2.5 pt-4">
            <Textarea
              rows={2}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (text.trim()) submit.mutate();
                }
              }}
              placeholder="Message Otto… (Enter to send, Shift+Enter for newline)"
              aria-label="Message"
              data-testid="command-composer"
            />
            <div className="flex flex-wrap items-center gap-2">
              <Select value={skillSlug} onChange={(e) => setSkillSlug(e.target.value)}
                      aria-label="Skill" className="h-9 text-[13px]">
                <option value="">No skill — free chat</option>
                {(skills ?? []).map((skill) => (
                  <option key={skill.slug} value={skill.slug}>{skill.name}</option>
                ))}
              </Select>
              <Select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}
                      aria-label="Execution mode" className="h-9 text-[13px]" data-testid="mode-select">
                <option value="read_only">Read-only</option>
                <option value="draft">Draft</option>
                <option value="act">Act (approvals apply)</option>
              </Select>
              <div className="ml-auto flex gap-2">
                {activeRun ? (
                  <>
                    <Button size="sm" variant="warn"
                            onClick={() => api.interruptRun(activeRun.id).then(() =>
                              queryClient.invalidateQueries({ queryKey: ["session-runs"] }))}>
                      <Pause className="size-3.5" /> Interrupt
                    </Button>
                    <Button size="sm" variant="danger"
                            onClick={() => api.cancelRun(activeRun.id).then(() =>
                              queryClient.invalidateQueries({ queryKey: ["session-runs"] }))}>
                      <OctagonX className="size-3.5" /> Cancel
                    </Button>
                  </>
                ) : null}
                <Button variant="primary" busy={submit.isPending} disabled={!text.trim()}
                        onClick={() => submit.mutate()} data-testid="command-send">
                  <Play className="size-4" /> Send
                </Button>
              </div>
            </div>
            {submit.isError ? (
              <p role="alert" className="text-[12.5px] text-danger">{(submit.error as Error).message}</p>
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
  const style = RUN_STATUS_STYLE[run.status] ?? { label: run.status, tone: "muted" as const };
  const reply = (run.result as { summary_md?: string } | null)?.summary_md;
  const isActive = ACTIVE_RUN_STATUSES.includes(run.status);

  return (
    <div className="space-y-2">
      {run.command_text ? (
        <div className="ml-auto max-w-[85%] rounded-[14px] rounded-br-[4px] bg-accent px-4 py-2.5 text-[14px] text-white w-fit">
          {run.command_text}
        </div>
      ) : null}
      <Card>
        <CardBody className="pt-4">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <Badge tone={style.tone}>{style.label}</Badge>
            <div className="flex items-center gap-2">
              {run.status === "interrupted" ? (
                <Button size="sm" variant="ghost"
                        onClick={() => api.resumeRun(run.id).then(() =>
                          queryClient.invalidateQueries({ queryKey: ["session-runs"] }))}>
                  <RotateCcw className="size-3.5" /> Resume
                </Button>
              ) : null}
              <button onClick={onToggle} className="text-[12px] text-muted hover:text-ink">
                {expanded ? "Hide timeline" : "Timeline"}
              </button>
            </div>
          </div>
          {reply ? (
            <div data-testid="assistant-reply"><Markdown content={reply} /></div>
          ) : isActive ? (
            <p className="stream-caret text-[14px] text-muted">Working</p>
          ) : run.error ? (
            <p className="text-[13.5px] text-danger">{run.error}</p>
          ) : (
            <p className="text-[13.5px] text-muted">{run.status_reason ?? "No reply."}</p>
          )}
          {expanded ? (
            <div className="mt-3 border-t border-line pt-3">
              <RunTimeline runId={run.id} />
              <ArtifactList runId={run.id} />
            </div>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}
