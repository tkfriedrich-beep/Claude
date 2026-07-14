"use client";

import { useState } from "react";
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Approval } from "@/lib/types";
import { ApprovalCard } from "@/components/cockpit/approval-card";
import { Badge } from "@/components/ui/badge";
import { CardSkeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { cn, fmtDate, fmtTime } from "@/lib/utils";
import { Hourglass, Scale, ShieldCheck } from "lucide-react";

// Tab keys double as the /approvals?status= filter the control plane expects.
const TABS = [
  { key: "pending", label: "PENDING" },
  { key: "approved,denied", label: "RESOLVED" },
  { key: "expired,cancelled", label: "EXPIRED" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

const VERDICT_TONE: Record<string, "accent" | "danger" | "muted"> = {
  approved: "accent",
  denied: "danger",
};

// A settled decision reads as a quiet ledger row — never an actionable card again.
function LedgerRow({ approval }: { approval: Approval }) {
  const at = approval.resolved_at ?? approval.requested_at;
  return (
    <li className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-4">
      <span className="w-[76px] flex-none font-mono text-[11.5px] leading-snug text-faint">
        {fmtTime(at)}
        <span className="block text-[10px]">{fmtDate(at)}</span>
      </span>
      <span className="min-w-0 flex-1 basis-52">
        <span className="block text-[14.5px] font-medium leading-snug">{approval.title}</span>
        <span className="mt-1 flex flex-wrap items-baseline gap-x-2 text-[12.5px] text-muted">
          <span className="font-mono text-[10.5px] tracking-[0.06em] text-muted-2">
            {approval.risk_level}
          </span>
          {approval.decision_note ? <span>“{approval.decision_note}”</span> : null}
        </span>
      </span>
      <Badge tone={VERDICT_TONE[approval.status] ?? "muted"}>{approval.status}</Badge>
    </li>
  );
}

export default function ApprovalsPage() {
  const [tab, setTab] = useState<TabKey>("pending");

  // All three lists stay warm so the tab tallies are live, not lazy.
  const pending = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => api.approvals("pending"),
    refetchInterval: 10_000,
  });
  const resolved = useQuery({
    queryKey: ["approvals", "approved,denied"],
    queryFn: () => api.approvals("approved,denied"),
    refetchInterval: 30_000,
  });
  const expired = useQuery({
    queryKey: ["approvals", "expired,cancelled"],
    queryFn: () => api.approvals("expired,cancelled"),
    refetchInterval: 30_000,
  });
  const queries: Record<TabKey, UseQueryResult<Approval[], Error>> = {
    pending,
    "approved,denied": resolved,
    "expired,cancelled": expired,
  };

  const active = queries[tab];
  const items = active.data ?? [];

  return (
    <div className="mx-auto max-w-[1560px] space-y-6">
      <header>
        <h1 className="text-[26px] font-semibold tracking-[-0.3px]">Decisions</h1>
        <p className="mt-1 text-[14px] text-muted">
          Every consequential action pauses here first. Nothing executes before you decide.
        </p>
      </header>

      <div role="tablist" aria-label="Approval status" className="flex flex-wrap gap-2">
        {TABS.map(({ key, label }) => {
          const count = queries[key].data?.length;
          const selected = tab === key;
          return (
            <button
              key={key}
              role="tab"
              aria-selected={selected}
              onClick={() => setTab(key)}
              className={cn(
                "rounded-full border px-4 py-[7px] font-mono text-[12px] font-medium tracking-[0.04em] transition-colors duration-200",
                selected
                  ? "border-(--accent-border) bg-accent-soft text-accent-hover"
                  : "border-line-control text-muted hover:text-accent-hover",
              )}
            >
              {label}
              {typeof count === "number" ? ` ${count}` : ""}
            </button>
          );
        })}
      </div>

      {active.isLoading ? (
        <CardSkeleton lines={5} />
      ) : active.error ? (
        <ErrorState detail={active.error.message} onRetry={() => active.refetch()} />
      ) : items.length === 0 ? (
        tab === "pending" ? (
          <EmptyState
            icon={<ShieldCheck />}
            title="The queue is clear."
            hint="Approvals will surface here calmly — and in the rail — the moment judgment is needed."
          />
        ) : tab === "approved,denied" ? (
          <EmptyState
            icon={<Scale />}
            title="Nothing resolved yet."
            hint="Every verdict — approved or denied, with your note — is recorded here."
          />
        ) : (
          <EmptyState
            icon={<Hourglass />}
            title="Nothing has expired."
            hint="Unanswered requests lapse safely — an expired approval never executes."
          />
        )
      ) : tab === "pending" ? (
        <div className="fadeup space-y-4" data-testid="approval-list">
          {items.map((approval) => (
            <ApprovalCard key={approval.id} approval={approval} />
          ))}
        </div>
      ) : (
        <ul
          className="fadeup divide-y divide-line-row rounded-[16px] border border-line-card bg-surface px-6"
          data-testid="approval-list"
        >
          {items.map((approval) => (
            <LedgerRow key={approval.id} approval={approval} />
          ))}
        </ul>
      )}
    </div>
  );
}
