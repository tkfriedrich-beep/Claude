"use client";

// Agents (/skills, was Skills) — the roster. Each card is a 1:1 presentation of a registry
// skill: monogram identity · mandate · risk grant · derived status · ▷ RUN · Configure.
// Same registry, same endpoints — presentation only (OttoOS spec §03).
import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Skill } from "@/lib/types";
import { AUTONOMY_LABEL } from "@/lib/types";
import { RiskBadge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { agentMetaFor, Monogram } from "@/components/ui/monogram";
import { CardSkeleton, EmptyState, ErrorState, SectionLabel } from "@/components/ui/states";
import { cn } from "@/lib/utils";
import { Search } from "lucide-react";

export default function SkillsPage() {
  const [query, setQuery] = useState("");
  const { data: skills, isLoading, error, refetch } = useQuery({
    queryKey: ["skills"], queryFn: api.skills,
  });

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return (skills ?? []).filter(
      (s) =>
        !q ||
        s.name.toLowerCase().includes(q) ||
        s.slug.toLowerCase().includes(q) ||
        agentMetaFor(s.slug, s.name).name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q),
    );
  }, [skills, query]);

  return (
    <div className="fadeup mx-auto w-full max-w-6xl space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[26px] font-semibold tracking-[-0.3px]">Agents</h1>
          <p className="mt-1 max-w-2xl text-[14px] text-muted">
            Versioned workflows with explicit tools, risk grants, and autonomy. Nothing acts
            beyond its grant.
          </p>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)}
                 placeholder="Search the roster…" className="w-64 pl-8" aria-label="Search skills" />
        </div>
      </header>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => <CardSkeleton key={i} />)}
        </div>
      ) : error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : filtered.length === 0 ? (
        <EmptyState
          title={query ? "No agents match." : "No agents on the roster."}
          hint={query ? `Nothing named “${query}”.` : "The skill registry returned nothing."}
        />
      ) : (
        <section className="space-y-4">
          <div className="flex flex-wrap items-baseline gap-3.5 px-1">
            <SectionLabel>Roster</SectionLabel>
            <span className="text-[13px] text-muted">{filtered.length} on staff</span>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid="skills-grid">
            {filtered.map((skill) => <AgentCard key={skill.slug} skill={skill} />)}
          </div>
        </section>
      )}
    </div>
  );
}

// Run affordance styled as the roster's mono pill; gold is selection/action, never status.
const runPill =
  "inline-flex h-7 items-center gap-1.5 rounded-full border border-(--accent-border) px-3.5 " +
  "font-mono text-[11.5px] font-medium text-accent transition-colors hover:bg-accent-soft " +
  "hover:text-accent-hover disabled:pointer-events-none disabled:opacity-50";

function AgentCard({ skill }: { skill: Skill }) {
  const router = useRouter();
  const run = useMutation({
    mutationFn: () => api.runSkill(skill.slug),
    onSuccess: (r) => router.push(`/history/${r.id}`),
  });
  const meta = agentMetaFor(skill.slug, skill.name);
  const needsInput = Boolean(
    ((skill.manifest?.input_schema as { required?: string[] })?.required ?? []).length,
  );
  // Status is derived from real registry fields only — this page has no run/approval data.
  const autonomy = AUTONOMY_LABEL[skill.autonomy] ?? `Level ${skill.autonomy}`;
  const status = skill.enabled
    ? { dot: "bg-ok", text: "text-muted-2", label: `Enabled · ${autonomy}` }
    : { dot: "bg-danger", text: "text-danger", label: `Disabled · ${autonomy}` };

  return (
    <Card className={cn("flex flex-col p-5", !skill.enabled && "opacity-60")}>
      <div className="flex items-center gap-3">
        <Monogram initials={meta.mono} state={skill.enabled ? "idle" : "blocked"} size={38} />
        <div className="min-w-0 flex-1">
          <Link href={`/skills/${skill.slug}`}
                className="block truncate text-[15.5px] font-semibold hover:text-accent-hover">
            {meta.name}
          </Link>
          <span className="block truncate font-mono text-[10.5px] text-muted-2">
            {skill.slug} · v{skill.version}
          </span>
        </div>
        <RiskBadge risk={skill.risk_level} />
      </div>

      <p className="mt-3 min-h-[40px] flex-1 text-[13px] leading-relaxed text-muted">
        {skill.description}
      </p>

      <div className="mt-3.5 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-line-row pt-3.5">
        <span className={cn("flex min-w-0 items-center gap-1.5 text-[12.5px]", status.text)}>
          <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", status.dot)} />
          <span className="truncate">{status.label}</span>
        </span>
        <div className="ml-auto flex shrink-0 items-center gap-2.5">
          <Link href={`/skills/${skill.slug}`}
                className="font-mono text-[11px] font-medium tracking-[0.06em] text-muted-2 transition-colors hover:text-ink">
            CONFIGURE →
          </Link>
          {needsInput ? (
            <Link href={`/skills/${skill.slug}`} className={runPill}
                  aria-label={`Run ${skill.name} (needs input)`}>
              ▷ RUN…
            </Link>
          ) : (
            <button type="button" className={runPill} disabled={!skill.enabled || run.isPending}
                    onClick={() => run.mutate()} data-testid={`run-${skill.slug}`}
                    aria-label={`Run ${skill.name}`}>
              {run.isPending ? (
                <span aria-hidden
                      className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : null}
              ▷ RUN
            </button>
          )}
        </div>
      </div>
    </Card>
  );
}
