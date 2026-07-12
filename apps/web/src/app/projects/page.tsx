"use client";

import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { FolderKanban, Play } from "lucide-react";

export default function ProjectsPage() {
  const router = useRouter();
  const { data: projects, isLoading, error, refetch } = useQuery({
    queryKey: ["projects"], queryFn: api.projects,
  });
  const pulse = useMutation({
    mutationFn: () => api.runSkill("project-pulse"),
    onSuccess: (run) => router.push(`/history/${run.id}`),
  });

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Projects</h1>
          <p className="text-[13px] text-muted">Backed by your vault&apos;s /projects notes and local records.</p>
        </div>
        <Button variant="primary" busy={pulse.isPending} onClick={() => pulse.mutate()}>
          <Play className="size-4" /> Run Project Pulse
        </Button>
      </header>

      {isLoading ? (
        <CardSkeleton lines={5} />
      ) : error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : (projects ?? []).length === 0 ? (
        <EmptyState icon={<FolderKanban />} title="No projects yet"
                    hint="Point onboarding/Settings at an Obsidian vault with a /projects folder." />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {(projects ?? []).map((project) => (
            <Card key={project.id}>
              <CardBody className="pt-4">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-[14.5px] font-semibold">{project.name}</p>
                  <Badge tone={project.status === "active" ? "accent" : "muted"}>{project.status}</Badge>
                </div>
                <p className="mt-1 text-[13px] text-muted">{project.description || "—"}</p>
                <p className="mt-2 flex items-center justify-between text-[12px] text-muted">
                  <span className="font-mono">{project.path ?? "no linked note"}</span>
                  <span>updated {timeAgo(project.updated_at)}</span>
                </p>
              </CardBody>
            </Card>
          ))}
        </div>
      )}
      <p className="text-[12.5px] text-muted">
        Movement, risks, and next actions live in the{" "}
        <Link href="/history" className="text-accent">latest Project Pulse report</Link>.
      </p>
    </div>
  );
}
