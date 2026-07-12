"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardBody } from "@/components/ui/card";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { Users } from "lucide-react";

export default function PeoplePage() {
  const { data: people, isLoading, error, refetch } = useQuery({
    queryKey: ["people"], queryFn: api.people,
  });

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <header>
        <h1 className="text-xl font-bold tracking-tight">People</h1>
        <p className="text-[13px] text-muted">
          Source-attributed relationship records. Richer people intelligence is on the roadmap.
        </p>
      </header>
      {isLoading ? (
        <CardSkeleton lines={4} />
      ) : error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : (people ?? []).length === 0 ? (
        <EmptyState icon={<Users />} title="No people recorded"
                    hint="People arrive via demo data today; approved memories can create them too." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {(people ?? []).map((person) => (
            <Card key={person.id}>
              <CardBody className="pt-4">
                <p className="text-[14.5px] font-semibold">{person.name}</p>
                <p className="text-[12.5px] text-accent">{person.relation}</p>
                <p className="mt-1.5 text-[13px] text-muted">{person.notes}</p>
                {person.source_ref ? (
                  <p className="mt-2 truncate font-mono text-[11px] text-muted" title={person.source_ref}>
                    source: {person.source_ref}
                  </p>
                ) : null}
              </CardBody>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
