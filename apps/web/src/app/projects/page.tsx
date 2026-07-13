"use client";

// Missions (/projects, was Projects) — two zones: the mission list (left) and the selected
// mission's dossier (right, client-side selection only). Everything rendered comes straight
// from /projects. Progress %, milestones, confidence, agent assignments and dependency
// flags are omitted until the backend grows those fields (spec step-6 follow-up) — never
// fabricated.
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { FolderKanban, Play } from "lucide-react";
import { api } from "@/lib/api";
import type { ProjectItem } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CardSkeleton, EmptyState, ErrorState, SectionLabel } from "@/components/ui/states";

function statusTone(status: string): "accent" | "muted" {
  return status === "active" ? "accent" : "muted";
}

export default function MissionsPage() {
  const router = useRouter();
  const { data: projects, isLoading, error, refetch } = useQuery({
    queryKey: ["projects"], queryFn: api.projects,
  });
  const pulse = useMutation({
    mutationFn: () => api.runSkill("project-pulse"),
    onSuccess: (run) => router.push(`/history/${run.id}`),
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const missions = projects ?? [];
  const selected = missions.find((m) => m.id === selectedId) ?? missions[0];

  return (
    <div className="flex flex-wrap items-start gap-7">
      {/* ── Zone 1 — the mission list ──────────────────────────────────── */}
      <div className="fadeup flex min-w-0 flex-[1_1_420px] flex-col gap-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Missions</h1>
            <p className="mt-1 text-[13px] text-muted">
              Backed by your vault&apos;s /projects notes and local records.
            </p>
          </div>
          <Button variant="primary" busy={pulse.isPending} onClick={() => pulse.mutate()}>
            <Play className="size-4" /> Run Project Pulse
          </Button>
        </header>

        {isLoading ? (
          <CardSkeleton lines={5} />
        ) : error ? (
          <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
        ) : missions.length === 0 ? (
          <EmptyState icon={<FolderKanban />} title="No missions yet."
                      hint="Point onboarding/Settings at an Obsidian vault with a /projects folder." />
        ) : (
          // Grid fallback below lg; a single-column selectable list beside the dossier above.
          <ul className="grid gap-3 md:grid-cols-2 lg:grid-cols-1" data-testid="mission-list">
            {missions.map((mission) => (
              <li key={mission.id}>
                <MissionRow
                  mission={mission}
                  selected={selected?.id === mission.id}
                  onSelect={() => setSelectedId(mission.id)}
                />
              </li>
            ))}
          </ul>
        )}

        <p className="text-[12.5px] text-muted">
          Movement, risks, and next actions live in the{" "}
          <Link href="/history" className="text-accent hover:text-accent-hover">
            latest Project Pulse report
          </Link>.
        </p>
      </div>

      {/* ── Zone 2 — selected mission dossier ──────────────────────────── */}
      {isLoading || selected ? (
        <div className="fadeup flex min-w-0 flex-[1.6_1_460px] flex-col gap-6">
          {selected ? <MissionDetail mission={selected} /> : <CardSkeleton lines={6} />}
        </div>
      ) : null}
    </div>
  );
}

function MissionRow({
  mission,
  selected,
  onSelect,
}: {
  mission: ProjectItem;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`Select mission ${mission.name}`}
      data-testid={`mission-row-${mission.slug}`}
      className={cn(
        "h-full w-full rounded-[14px] border px-6 py-5 text-left transition-colors",
        selected
          ? "border-(--accent-border) bg-accent-soft"
          : "border-line-card bg-surface hover:border-line-button",
      )}
    >
      <div className="flex items-center gap-3">
        <span className="min-w-0 flex-1 truncate text-[16px] font-semibold tracking-[-0.01em]">
          {mission.name}
        </span>
        <Badge tone={statusTone(mission.status)}>{mission.status}</Badge>
      </div>
      <p className="mt-1.5 line-clamp-2 font-serif text-[14px] italic leading-snug text-muted">
        {mission.description || "—"}
      </p>
      <div className="mt-3 flex items-baseline gap-3 font-mono text-[11px] text-faint">
        <span className="min-w-0 flex-1 truncate">{mission.path ?? "no linked note"}</span>
        <span className="shrink-0">UPDATED {timeAgo(mission.updated_at).toUpperCase()}</span>
      </div>
    </button>
  );
}

function MissionDetail({ mission }: { mission: ProjectItem }) {
  return (
    <div className="flex flex-col gap-6" data-testid="mission-detail">
      <Card className="px-7 py-7 sm:px-9 sm:py-8">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h2 className="text-[24px] font-semibold tracking-[-0.01em]">{mission.name}</h2>
          <Badge tone={statusTone(mission.status)}>{mission.status}</Badge>
        </div>
        {mission.description ? (
          <p className="mt-3 font-serif text-[19px] italic leading-snug text-ink-soft">
            “{mission.description}”
          </p>
        ) : (
          <p className="mt-3 text-[14px] text-muted">—</p>
        )}
        <div className="my-6 h-px bg-line-row" aria-hidden />
        <div className="grid gap-x-7 gap-y-5 sm:grid-cols-2">
          <div className="min-w-0">
            <SectionLabel>Vault note</SectionLabel>
            <p className="mt-1.5 break-all font-mono text-[12.5px] text-ink-soft">
              {mission.path ?? "no linked note"}
            </p>
          </div>
          <div>
            <SectionLabel>Updated</SectionLabel>
            <p className="mt-1.5 font-mono text-[12.5px] text-ink-soft">
              {timeAgo(mission.updated_at)}
            </p>
          </div>
        </div>
      </Card>

      <Card className="px-6 py-6 sm:px-7">
        <SectionLabel>Evidence — documents</SectionLabel>
        <ul className="mt-2">
          <li className="flex items-baseline gap-3 border-b border-line-row py-3">
            <span className="min-w-0 flex-1 break-all font-mono text-[12px] text-ink-soft">
              {mission.path ?? "no linked note"}
            </span>
            <span className="shrink-0 font-mono text-[10px] tracking-[0.08em] text-faint">
              VAULT NOTE
            </span>
          </li>
          <li className="py-3">
            <Link href="/history" className="group flex items-baseline gap-3">
              <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-accent group-hover:text-accent-hover">
                Latest Project Pulse report
              </span>
              <span className="shrink-0 font-mono text-[10px] tracking-[0.08em] text-faint group-hover:text-accent-hover">
                OPEN →
              </span>
            </Link>
          </li>
        </ul>
      </Card>
    </div>
  );
}
