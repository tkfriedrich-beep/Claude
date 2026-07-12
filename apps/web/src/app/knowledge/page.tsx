"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Library, RefreshCw, Search } from "lucide-react";

export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const { data, error, isFetching, refetch } = useQuery({
    queryKey: ["knowledge", submitted],
    queryFn: () => api.knowledgeSearch(submitted),
    enabled: submitted.length > 0,
  });
  const reindex = useMutation({
    mutationFn: api.knowledgeReindex,
    onSuccess: () => submitted && refetch(),
  });

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Knowledge</h1>
          <p className="text-[13px] text-muted">
            Full-text search over your vault and local sources. Files stay canonical — this is
            only an index (semantic retrieval is a roadmap upgrade).
          </p>
        </div>
        <Button size="sm" busy={reindex.isPending} onClick={() => reindex.mutate()}>
          <RefreshCw className="size-3.5" /> Reindex
        </Button>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(query.trim());
        }}
        className="relative"
      >
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
        <Input value={query} onChange={(e) => setQuery(e.target.value)}
               placeholder="Search your notes… (press Enter)" className="h-11 pl-9"
               aria-label="Knowledge search" />
      </form>

      {error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : !submitted ? (
        <EmptyState icon={<Library />} title="Search your local knowledge"
                    hint="Try “Nordwind”, “studio”, or “pricing” with the demo vault." />
      ) : isFetching ? (
        <p className="text-[13px] text-muted">Searching…</p>
      ) : (data?.results ?? []).length === 0 ? (
        <EmptyState title={`No matches for “${submitted}”`}
                    hint="Rebuild the index if you recently added files." />
      ) : (
        <ul className="space-y-2">
          {data!.results.map((result, i) => (
            <Card key={i}>
              <CardBody className="pt-3.5">
                <p className="text-[14px] font-semibold">{result.title}</p>
                <p className="truncate font-mono text-[11px] text-muted">{result.path}</p>
                <p className="mt-1.5 text-[13px] text-muted"
                   dangerouslySetInnerHTML={{
                     __html: result.snippet
                       .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
                       .replaceAll("⟪", "<mark class='bg-accent-soft text-accent rounded px-0.5'>")
                       .replaceAll("⟫", "</mark>"),
                   }} />
              </CardBody>
            </Card>
          ))}
        </ul>
      )}
    </div>
  );
}
