"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ApprovalCard } from "@/components/cockpit/approval-card";
import { cn } from "@/lib/utils";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { ShieldCheck } from "lucide-react";

const TABS = [
  { key: "pending", label: "Pending" },
  { key: "approved,denied", label: "Resolved" },
  { key: "expired,cancelled", label: "Expired" },
] as const;

export default function ApprovalsPage() {
  const [tab, setTab] = useState<string>("pending");
  const { data: approvals, isLoading, error, refetch } = useQuery({
    queryKey: ["approvals", tab],
    queryFn: () => api.approvals(tab),
    refetchInterval: tab === "pending" ? 10_000 : false,
  });

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <header>
        <h1 className="text-xl font-bold tracking-tight">Approvals</h1>
        <p className="text-[13px] text-muted">
          Every consequential action pauses here first. Nothing executes before you decide.
        </p>
      </header>

      <div role="tablist" aria-label="Approval status" className="flex gap-1 rounded-[12px] border border-line bg-surface p-1 w-fit">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "rounded-[9px] px-3.5 py-1.5 text-[13px] font-medium",
              tab === key ? "bg-accent text-white" : "text-muted hover:text-ink",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <CardSkeleton lines={5} />
      ) : error ? (
        <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
      ) : (approvals ?? []).length === 0 ? (
        <EmptyState
          icon={<ShieldCheck />}
          title={tab === "pending" ? "Nothing needs your approval" : "Nothing here"}
          hint={
            tab === "pending"
              ? "When a skill or session proposes a side effect, the full preview lands here."
              : undefined
          }
        />
      ) : (
        <div className="space-y-3" data-testid="approval-list">
          {(approvals ?? []).map((approval) => (
            <ApprovalCard key={approval.id} approval={approval} />
          ))}
        </div>
      )}
    </div>
  );
}
