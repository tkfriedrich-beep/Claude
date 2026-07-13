"use client";

// Knowledge (/knowledge) — full-text search over the local vault. The mono status inside
// the search bar is live: match count once a query ran, "SEARCHING…" mid-flight, and the
// real indexed-note count the API returned after a reindex — never an invented number.
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";

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

  const matches = data?.results.length;
  const status = isFetching
    ? "SEARCHING…"
    : error
      ? "ERROR"
      : matches !== undefined
        ? `${matches} ${matches === 1 ? "MATCH" : "MATCHES"}`
        : reindex.data
          ? `FTS · ${reindex.data.indexed} ${reindex.data.indexed === 1 ? "NOTE" : "NOTES"}`
          : "FTS";

  return (
    <div className="mx-auto max-w-[1360px] space-y-[22px]">
      <header className="fadeup flex flex-wrap items-baseline justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Knowledge</h1>
          <p className="mt-1 text-[13px] text-muted">
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
        className="fadeup flex items-center gap-3.5 rounded-[12px] border border-line-control bg-raised px-5 py-3.5 transition-colors focus-within:border-accent"
      >
        <span aria-hidden className="text-[15px] text-faint">
          ⌕
        </span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search your notes… (press Enter)"
          aria-label="Knowledge search"
          className="min-w-0 flex-1 bg-transparent text-[15.5px] text-ink outline-none placeholder:text-muted/70"
        />
        <span aria-live="polite" className="shrink-0 font-mono text-[11px] tracking-[0.08em] text-faint">
          {status}
        </span>
      </form>

      {reindex.isError ? (
        <p className="text-[12.5px] text-danger">Reindex failed — {reindex.error.message}</p>
      ) : null}

      {error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : !submitted ? (
        <EmptyState
          title="Search your local knowledge."
          hint="Try “Nordwind”, “studio”, or “pricing” with the demo vault."
          action={
            <p className="text-[12.5px] text-muted-2">
              {reindex.data ? `${reindex.data.indexed} notes indexed · ` : null}
              semantic retrieval is a roadmap upgrade
            </p>
          }
        />
      ) : isFetching ? (
        <div className="space-y-3">
          <CardSkeleton lines={2} />
          <CardSkeleton lines={2} />
        </div>
      ) : !data || data.results.length === 0 ? (
        <EmptyState
          title={`No matches for “${submitted}”`}
          hint="Rebuild the index if you recently added files."
        />
      ) : (
        <ul className="space-y-3">
          {data.results.map((result, i) => (
            <li key={i} className="fadeup">
              <Card className="px-7 py-[22px] transition-colors hover:border-line-control">
                <div className="flex items-baseline gap-4">
                  <p className="min-w-0 flex-1 truncate text-[15.5px] font-semibold">
                    {result.title}
                  </p>
                  <p className="max-w-[45%] truncate font-mono text-[10.5px] text-faint">
                    {result.path}
                  </p>
                </div>
                <p
                  className="mt-1.5 text-[13.5px] leading-relaxed text-muted"
                  dangerouslySetInnerHTML={{
                    __html: result.snippet
                      .replaceAll("&", "&amp;")
                      .replaceAll("<", "&lt;")
                      .replaceAll(">", "&gt;")
                      .replaceAll("⟪", "<mark class='bg-accent-soft text-accent rounded px-0.5'>")
                      .replaceAll("⟫", "</mark>"),
                  }}
                />
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
