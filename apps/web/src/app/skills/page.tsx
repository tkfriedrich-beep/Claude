"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AUTONOMY_LABEL } from "@/lib/types";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { Play, Search } from "lucide-react";

export default function SkillsPage() {
  const [query, setQuery] = useState("");
  const { data: skills, isLoading, error, refetch } = useQuery({
    queryKey: ["skills"], queryFn: api.skills,
  });

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return (skills ?? []).filter(
      (s) => !q || s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q),
    );
  }, [skills, query]);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Skills</h1>
          <p className="text-[13px] text-muted">
            Versioned workflows with explicit tools, risk, and autonomy. Nothing acts beyond its grant.
          </p>
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)}
                 placeholder="Search skills…" className="w-64 pl-8" aria-label="Search skills" />
        </div>
      </header>

      {isLoading ? (
        <div className="grid gap-3 md:grid-cols-2">{[1, 2, 3, 4].map((i) => <CardSkeleton key={i} />)}</div>
      ) : error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : filtered.length === 0 ? (
        <EmptyState title="No skills match" hint={`Nothing named “${query}”.`} />
      ) : (
        <div className="grid gap-3 md:grid-cols-2" data-testid="skills-grid">
          {filtered.map((skill) => <SkillRow key={skill.slug} skill={skill} />)}
        </div>
      )}
    </div>
  );
}

function SkillRow({ skill }: { skill: { slug: string; name: string; description: string; version: string; risk_level: string; autonomy: number; enabled: boolean; manifest: Record<string, unknown> } }) {
  const router = useRouter();
  const run = useMutation({
    mutationFn: () => api.runSkill(skill.slug),
    onSuccess: (r) => router.push(`/history/${r.id}`),
  });
  const needsInput = Boolean(
    ((skill.manifest?.input_schema as { required?: string[] })?.required ?? []).length,
  );
  return (
    <Card className={!skill.enabled ? "opacity-60" : undefined}>
      <CardBody className="flex h-full flex-col pt-4">
        <div className="flex items-start justify-between gap-2">
          <Link href={`/skills/${skill.slug}`} className="text-[15px] font-semibold hover:text-accent">
            {skill.name}
          </Link>
          <RiskBadge risk={skill.risk_level} />
        </div>
        <p className="mt-1 flex-1 text-[13px] text-muted">{skill.description}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge tone="outline">v{skill.version}</Badge>
          <Badge tone="outline">{AUTONOMY_LABEL[skill.autonomy]}</Badge>
          {!skill.enabled ? <Badge tone="danger">disabled</Badge> : null}
          <div className="ml-auto flex gap-2">
            <Link href={`/skills/${skill.slug}`}>
              <Button size="sm" variant="ghost">Configure</Button>
            </Link>
            {needsInput ? (
              <Link href={`/skills/${skill.slug}`}>
                <Button size="sm" variant="primary"><Play className="size-3.5" /> Run…</Button>
              </Link>
            ) : (
              <Button size="sm" variant="primary" busy={run.isPending} disabled={!skill.enabled}
                      onClick={() => run.mutate()} data-testid={`run-${skill.slug}`}>
                <Play className="size-3.5" /> Run now
              </Button>
            )}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
