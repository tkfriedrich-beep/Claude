"use client";

// Automations (/automations) — the schedule ledger. Scheduled agents start in Shadow Mode
// and graduate (Shadow → Draft → Act with approval) only by a deliberate human choice made
// in this panel — Otto never promotes itself. Same endpoints and controls — presentation only.
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Schedule } from "@/lib/types";
import { cn, fmtDate, fmtTime, RUN_STATUS_STYLE } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { agentMetaFor } from "@/components/ui/monogram";
import { CardSkeleton, EmptyState, ErrorState, SectionLabel } from "@/components/ui/states";
import { Switch } from "@/components/ui/switch";
import { Plus, Repeat } from "lucide-react";

// Last-run status reuses the run ledger's tone vocabulary — the word is the status,
// color only reinforces it.
const STATUS_TEXT: Record<string, string> = {
  accent: "text-accent-hover",
  warn: "text-warn",
  danger: "text-danger",
  muted: "text-muted-2",
};

function statusClass(status: string | null): string {
  const tone = (status ? RUN_STATUS_STYLE[status]?.tone : undefined) ?? "accent";
  return STATUS_TEXT[tone] ?? "text-accent-hover";
}

export default function AutomationsPage() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const { data: automations, isLoading, error, refetch } = useQuery({
    queryKey: ["automations"], queryFn: api.automations,
  });

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      api.patchAutomation(id, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["automations"] }),
  });
  const runNow = useMutation({
    mutationFn: (id: string) => api.runAutomationNow(id),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["automations"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const list = automations ?? [];

  return (
    <div className="fadeup mx-auto w-full max-w-4xl space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[26px] font-semibold tracking-[-0.3px]">Automations</h1>
          <p className="mt-1 max-w-2xl text-[14px] text-muted">
            Scheduled agents start in{" "}
            <strong className="font-semibold text-ink-soft">Shadow Mode</strong>: they run and
            show what they <em>would</em> have done — real actions only after you graduate them
            deliberately.
          </p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" /> New automation
        </Button>
      </header>

      {isLoading ? (
        <CardSkeleton lines={4} />
      ) : error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : list.length === 0 ? (
        <EmptyState icon={<Repeat />} title="No automations yet"
                    hint="Schedule Morning Brief or Project Pulse — Shadow Mode keeps them harmless while you build trust."
                    action={<Button onClick={() => setCreateOpen(true)}>Create one</Button>} />
      ) : (
        <section className="space-y-3.5">
          <div className="flex flex-wrap items-baseline gap-3.5 px-1">
            <SectionLabel>Schedule ledger</SectionLabel>
            <span className="text-[13px] text-muted">{list.length} scheduled</span>
          </div>
          <div className="space-y-3" data-testid="automation-list">
            {list.map((schedule) => (
              <ScheduleCard key={schedule.id} schedule={schedule}
                            onPatch={(body) => patch.mutate({ id: schedule.id, body })}
                            onRunNow={() => runNow.mutate(schedule.id)}
                            runBusy={runNow.isPending} />
            ))}
          </div>
        </section>
      )}

      {!isLoading && !error ? (
        <p className="border-t border-line-row px-1 pt-3.5 text-[12.5px] leading-relaxed text-faint">
          Graduation path:{" "}
          <span className="text-muted">Shadow → Draft → Act with approval</span>. Each step is a
          deliberate choice in this panel — Otto never promotes itself.
        </p>
      ) : null}

      <CreateAutomationDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}

function ScheduleCard({
  schedule,
  onPatch,
  onRunNow,
  runBusy,
}: {
  schedule: Schedule;
  onPatch: (body: Record<string, unknown>) => void;
  onRunNow: () => void;
  runBusy: boolean;
}) {
  const agent = agentMetaFor(schedule.skill_slug, schedule.name);
  const interval = schedule.interval_minutes >= 1440
    ? `${Math.round(schedule.interval_minutes / 1440)}d`
    : `${schedule.interval_minutes}m`;

  return (
    <Card className="px-6 py-5">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <div className="min-w-0 flex-1 basis-64">
          <p className="truncate text-[16px] font-semibold tracking-[-0.01em]">{schedule.name}</p>
          <p className="mt-1 text-[13px] text-muted">
            {agent.name} agent · every {interval} · next{" "}
            <span className="font-mono text-[12px] text-ink-soft">
              {schedule.next_run_at
                ? `${fmtDate(schedule.next_run_at)} ${fmtTime(schedule.next_run_at)}`
                : "—"}
            </span>
            {schedule.last_run_id ? (
              <>
                {" · last "}
                <Link className={cn("hover:underline", statusClass(schedule.last_run_status))}
                      href={`/history/${schedule.last_run_id}`}>
                  {schedule.last_run_status ?? "view"}
                </Link>
              </>
            ) : " · never ran"}
          </p>
        </div>
        {schedule.shadow_mode ? <Badge tone="warn">shadow</Badge> : <Badge tone="accent">live</Badge>}
        {schedule.enabled ? <Badge tone="accent">on</Badge> : <Badge tone="muted">paused</Badge>}
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-2">enabled</span>
          <Switch checked={schedule.enabled} label={`${schedule.name} enabled`}
                  onChange={(v) => onPatch({ enabled: v })} />
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-2">shadow</span>
          <Switch checked={schedule.shadow_mode} label={`${schedule.name} shadow mode`}
                  onChange={(v) => onPatch({ shadow_mode: v })} />
        </div>
        <Button size="sm" busy={runBusy} onClick={onRunNow} aria-label={`Run ${schedule.name} now`}>
          ▷ Run now
        </Button>
      </div>
    </Card>
  );
}

function CreateAutomationDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data: skills } = useQuery({ queryKey: ["skills"], queryFn: api.skills, enabled: open });
  const [skillSlug, setSkillSlug] = useState("morning-brief");
  const [intervalMinutes, setIntervalMinutes] = useState(1440);
  const [shadow, setShadow] = useState(true);

  const create = useMutation({
    mutationFn: () =>
      api.createAutomation({
        skill_slug: skillSlug,
        interval_minutes: intervalMinutes,
        shadow_mode: shadow,
        start_in_minutes: 1,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automations"] });
      onClose();
    },
  });

  const schedulable = (skills ?? []).filter((s) => (s.manifest as any)?.supports_schedule !== false);

  return (
    <Dialog open={open} onClose={onClose} title="New automation">
      <div className="space-y-4">
        <Field label="Agent">
          <Select value={skillSlug} onChange={(e) => setSkillSlug(e.target.value)} className="w-full">
            {schedulable.map((skill) => {
              const meta = agentMetaFor(skill.slug, skill.name);
              return (
                <option key={skill.slug} value={skill.slug}>
                  {meta.name === skill.name ? skill.name : `${meta.name} · ${skill.name}`}
                </option>
              );
            })}
          </Select>
        </Field>
        <Field label="Interval (minutes)" hint="1440 = daily. Minimum 15.">
          <Input type="number" min={15} value={intervalMinutes}
                 onChange={(e) => setIntervalMinutes(Number(e.target.value))} />
        </Field>
        <div className="flex items-center justify-between gap-4 rounded-[11px] border border-(--warn-border) bg-warn-surface px-4 py-3.5">
          <div>
            <p className="text-[13.5px] font-medium text-warn">Shadow Mode</p>
            <p className="mt-0.5 text-[12.5px] text-muted">
              Strongly recommended for new automations — previews instead of real actions.
            </p>
          </div>
          <Switch checked={shadow} onChange={setShadow} label="Shadow mode" />
        </div>
        {create.isError ? <ErrorState detail={(create.error as Error).message} /> : null}
        <Button variant="primary" className="w-full" busy={create.isPending} onClick={() => create.mutate()}>
          Create automation
        </Button>
      </div>
    </Dialog>
  );
}
