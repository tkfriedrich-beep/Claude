"use client";

// Relationships (/people, was People) — source-attributed person cards. The NEXT TOUCH
// row is derived from real /agenda commitments (soonest one whose title mentions the
// person's first name) — never invented. Richer people intelligence stays a roadmap note.
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { api } from "@/lib/api";
import type { AgendaResponse, PersonItem } from "@/lib/types";
import { fmtDate } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { Monogram } from "@/components/ui/monogram";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";

type Commitment = AgendaResponse["commitments"][number];

function initialsOf(name: string): string {
  const initials = name
    .trim()
    .split(/\s+/)
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return initials || "?";
}

function nextTouchFor(person: PersonItem, commitments: Commitment[]): Commitment | null {
  const first = person.name.trim().split(/\s+/)[0]?.toLowerCase();
  if (!first) return null;
  return commitments.find((c) => c.title.toLowerCase().includes(first)) ?? null;
}

export default function RelationshipsPage() {
  const { data: people, isLoading, error, refetch } = useQuery({
    queryKey: ["people"], queryFn: api.people,
  });
  // Commitments feed the NEXT TOUCH rows; if agenda fails, the rows simply stay hidden.
  const { data: agenda } = useQuery({ queryKey: ["agenda"], queryFn: api.agenda });

  // Due-date ascending (undated last) so `find` returns the soonest touch per person.
  const commitments = useMemo(() => {
    return [...(agenda?.commitments ?? [])].sort((a, b) => {
      if (!a.due_at) return b.due_at ? 1 : 0;
      if (!b.due_at) return -1;
      return new Date(a.due_at).getTime() - new Date(b.due_at).getTime();
    });
  }, [agenda]);

  const grid = "grid grid-cols-[repeat(auto-fit,minmax(min(380px,100%),1fr))] gap-[22px]";

  return (
    <div className="mx-auto max-w-[1560px] space-y-6">
      <header className="fadeup">
        <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Relationships</h1>
        <p className="mt-1 text-[13px] text-muted">
          Source-attributed people records — every claim traces to a note you own. Richer
          people intelligence is on the roadmap.
        </p>
      </header>
      {isLoading ? (
        <div className={grid}>
          {Array.from({ length: 3 }).map((_, i) => (
            <CardSkeleton key={i} lines={3} />
          ))}
        </div>
      ) : error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : (people ?? []).length === 0 ? (
        <EmptyState icon={<Users />} title="No people recorded"
                    hint="People arrive via demo data today; approved memories can create them too." />
      ) : (
        <div className={`fadeup ${grid}`} data-testid="people-grid">
          {(people ?? []).map((person) => (
            <PersonCard key={person.id} person={person} touch={nextTouchFor(person, commitments)} />
          ))}
        </div>
      )}
    </div>
  );
}

function PersonCard({ person, touch }: { person: PersonItem; touch: Commitment | null }) {
  return (
    <Card
      className="px-[30px] py-[26px] transition-colors hover:border-line-button"
      data-testid="person-card"
    >
      <div className="flex items-center gap-3.5">
        {/* state="working" borrows the gold ring — people monograms are gold in the spec */}
        <Monogram initials={initialsOf(person.name)} state="working" size={42} />
        <div className="min-w-0">
          <p className="truncate text-[17px] font-semibold tracking-[-0.01em]">{person.name}</p>
          <p className="mt-0.5 text-[13px] text-accent-hover">{person.relation}</p>
        </div>
      </div>
      <p className="mt-3.5 min-h-11 text-[14px] text-muted">{person.notes}</p>
      {touch || person.source_ref ? (
        <div className="mt-3.5 flex items-baseline gap-3">
          {touch ? (
            <span
              className="min-w-0 flex-1 truncate font-mono text-[11px] font-medium text-warn"
              data-testid="person-next-touch"
              title={touch.title}
            >
              NEXT TOUCH — {touch.title}
              {touch.due_at ? ` · ${fmtDate(touch.due_at).toUpperCase()}` : ""}
            </span>
          ) : null}
          {person.source_ref ? (
            <span
              className="ml-auto min-w-0 shrink truncate font-mono text-[10.5px] text-faint"
              title={person.source_ref}
            >
              {person.source_ref}
            </span>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
