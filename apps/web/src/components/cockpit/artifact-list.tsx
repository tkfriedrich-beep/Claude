"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Artifact } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Markdown } from "@/components/ui/markdown";
import { Button } from "@/components/ui/button";
import { Download, FileText } from "lucide-react";

export function ArtifactList({ runId }: { runId: string }) {
  const { data: artifacts } = useQuery({
    queryKey: ["artifacts", runId],
    queryFn: () => api.artifacts(runId),
  });
  const [openArtifact, setOpenArtifact] = useState<Artifact | null>(null);

  if (!artifacts || artifacts.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="mb-1.5 text-[12px] font-semibold uppercase tracking-wide text-muted">
        Artifacts
      </p>
      <div className="flex flex-wrap gap-2" data-testid="artifact-list">
        {artifacts.map((artifact) => (
          <button
            key={artifact.id}
            onClick={() => setOpenArtifact(artifact)}
            className="flex items-center gap-1.5 rounded-full border border-line bg-raised px-3 py-1.5 text-[12.5px] font-medium hover:border-accent/50"
          >
            <FileText className="size-3.5 text-accent" />
            {artifact.title}
            <Badge tone="outline">{artifact.kind}</Badge>
          </button>
        ))}
      </div>
      <ArtifactViewer artifact={openArtifact} onClose={() => setOpenArtifact(null)} />
    </div>
  );
}

export function ArtifactViewer({
  artifact,
  onClose,
}: {
  artifact: Artifact | null;
  onClose: () => void;
}) {
  const { data: content } = useQuery({
    queryKey: ["artifact", artifact?.id],
    queryFn: () => api.artifact(artifact!.id),
    enabled: Boolean(artifact),
  });
  return (
    <Dialog open={Boolean(artifact)} onClose={onClose} title={artifact?.title ?? "Artifact"} wide>
      {content ? (
        <>
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-[12px] text-muted">
              <Badge tone="outline">{content.kind}</Badge>
              {typeof content.meta?.generation_mode === "string" ? (
                <Badge tone={content.meta.generation_mode === "llm_assisted" ? "accent" : "muted"}>
                  {String(content.meta.generation_mode)}
                </Badge>
              ) : null}
            </div>
            <a href={api.artifactDownloadUrl(content.id)} download>
              <Button size="sm"><Download className="size-3.5" /> Download</Button>
            </a>
          </div>
          {content.missing_file ? (
            <p className="text-[13px] text-danger">The artifact file is missing on disk.</p>
          ) : content.kind === "markdown" ? (
            <Markdown content={content.content ?? ""} />
          ) : (
            <pre className="max-h-[60dvh] overflow-auto rounded-[10px] border border-line bg-raised p-3 font-mono text-[12px]">
              {content.content}
            </pre>
          )}
        </>
      ) : (
        <p className="text-sm text-muted">Loading…</p>
      )}
    </Dialog>
  );
}
