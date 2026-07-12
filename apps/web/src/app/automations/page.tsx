"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtDate, fmtTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { Play, Plus, Repeat } from "lucide-react";

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

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Automations</h1>
          <p className="text-[13px] text-muted">
            Scheduled skills start in <strong>Shadow Mode</strong>: they run and show what they
            <em> would</em> have done — real actions only after you graduate them deliberately.
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
      ) : (automations ?? []).length === 0 ? (
        <EmptyState icon={<Repeat />} title="No automations yet"
                    hint="Schedule Morning Brief or Project Pulse — Shadow Mode keeps them harmless while you build trust."
                    action={<Button variant="primary" onClick={() => setCreateOpen(true)}>Create one</Button>} />
      ) : (
        <div className="space-y-3" data-testid="automation-list">
          {(automations ?? []).map((schedule) => (
            <Card key={schedule.id}>
              <CardBody className="flex flex-wrap items-center gap-3 pt-4">
                <div className="min-w-0 flex-1">
                  <p className="text-[14.5px] font-semibold">{schedule.name}</p>
                  <p className="text-[12.5px] text-muted">
                    every {schedule.interval_minutes >= 1440
                      ? `${Math.round(schedule.interval_minutes / 1440)}d`
                      : `${schedule.interval_minutes}m`}
                    {" · next "}
                    {schedule.next_run_at ? `${fmtDate(schedule.next_run_at)} ${fmtTime(schedule.next_run_at)}` : "—"}
                    {schedule.last_run_id ? (
                      <>
                        {" · last "}
                        <Link className="text-accent hover:underline" href={`/history/${schedule.last_run_id}`}>
                          {schedule.last_run_status ?? "view"}
                        </Link>
                      </>
                    ) : " · never ran"}
                  </p>
                </div>
                {schedule.shadow_mode ? <Badge tone="warn">shadow</Badge> : <Badge tone="accent">live</Badge>}
                <div className="flex items-center gap-1.5">
                  <span className="text-[12px] text-muted">{schedule.enabled ? "on" : "paused"}</span>
                  <Switch checked={schedule.enabled} label={`${schedule.name} enabled`}
                          onChange={(v) => patch.mutate({ id: schedule.id, body: { enabled: v } })} />
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[12px] text-muted">shadow</span>
                  <Switch checked={schedule.shadow_mode} label={`${schedule.name} shadow mode`}
                          onChange={(v) => patch.mutate({ id: schedule.id, body: { shadow_mode: v } })} />
                </div>
                <Button size="sm" busy={runNow.isPending} onClick={() => runNow.mutate(schedule.id)}>
                  <Play className="size-3.5" /> Run now
                </Button>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      <CreateAutomationDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
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
        <Field label="Skill">
          <Select value={skillSlug} onChange={(e) => setSkillSlug(e.target.value)} className="w-full">
            {schedulable.map((skill) => (
              <option key={skill.slug} value={skill.slug}>{skill.name}</option>
            ))}
          </Select>
        </Field>
        <Field label="Interval (minutes)" hint="1440 = daily. Minimum 15.">
          <Input type="number" min={15} value={intervalMinutes}
                 onChange={(e) => setIntervalMinutes(Number(e.target.value))} />
        </Field>
        <div className="flex items-center justify-between rounded-[10px] border border-warn/40 bg-warn-soft/50 px-3.5 py-3">
          <div>
            <p className="text-[13.5px] font-medium">Shadow Mode</p>
            <p className="text-[12.5px] text-muted">
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
