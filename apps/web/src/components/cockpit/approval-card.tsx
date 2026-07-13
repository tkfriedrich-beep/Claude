"use client";

// Canonical decision card (OttoOS spec §03) — preserves approval-card fields FIELD-FOR-FIELD:
// title + risk chip · requested/expires mono · what/why · target/reversibility(+cost) ·
// before/after diff well · ▸ technical details JSON · note → audit trail ·
// Approve once / Modify / Deny / Cancel the run. "Always allow" lives ONLY in
// Settings → Policies. R4 demands a typed phrase. Keyboard on focused card: a approve · d deny.
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Approval } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorState } from "@/components/ui/states";

const CONFIRM_PHRASE = "I understand the risk";

function DiffWell({ diff }: { diff: string }) {
  return (
    <pre className="max-h-56 overflow-auto rounded-[9px] border border-line-row bg-well p-3.5 font-mono text-[11.5px] leading-relaxed">
      {diff.split("\n").map((line, i) => (
        <span
          key={i}
          className={cn(
            "block",
            line.startsWith("+") && !line.startsWith("+++")
              ? "text-diff-add"
              : line.startsWith("-") && !line.startsWith("---")
                ? "text-danger"
                : undefined,
          )}
        >
          {line}
        </span>
      ))}
    </pre>
  );
}

export function ApprovalCard({
  approval,
  compact,
  onModify,
}: {
  approval: Approval;
  compact?: boolean;
  onModify?: () => void;
}) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const [confirmPhrase, setConfirmPhrase] = useState("");
  const [error, setError] = useState<string | null>(null);

  const resolve = useMutation({
    mutationFn: (decision: "approve" | "deny") =>
      api.resolveApproval(approval.id, {
        decision,
        note,
        confirm_phrase: approval.confirm_phrase_required ? confirmPhrase : undefined,
      }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["briefing"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const cancelRun = useMutation({
    mutationFn: () => api.cancelRun(approval.run_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    },
  });

  const pending = approval.status === "pending";
  const approveBlocked =
    approval.confirm_phrase_required && confirmPhrase.trim() !== CONFIRM_PHRASE;

  return (
    <div
      data-testid="approval-card"
      tabIndex={pending ? 0 : undefined}
      onKeyDown={(e) => {
        // a / d act only when the card itself is focused — never while typing in a field.
        if (!pending || e.target !== e.currentTarget) return;
        if (e.key === "a" && !approveBlocked) resolve.mutate("approve");
        if (e.key === "d") resolve.mutate("deny");
      }}
      className={cn(
        "rounded-[16px] border bg-surface",
        // The only amber-tinted surface in the system (spec §03).
        pending ? "border-(--warn-border) bg-warn-surface" : "border-line-card",
      )}
    >
      <div className="space-y-3.5 p-6">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-[15.5px] font-semibold leading-snug">{approval.title}</h3>
            <p className="mt-1 font-mono text-[11px] text-muted-2">
              requested {timeAgo(approval.requested_at)}
              {approval.expires_at && pending ? (
                <> · expires in {timeAgo(approval.expires_at).replace(" ago", "")}</>
              ) : null}
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <RiskBadge risk={approval.risk_level} />
            {!pending ? (
              <Badge
                tone={
                  approval.status === "approved"
                    ? "accent"
                    : approval.status === "denied"
                      ? "danger"
                      : "muted"
                }
              >
                {approval.status}
              </Badge>
            ) : null}
          </div>
        </div>

        <dl className="grid gap-x-8 gap-y-2 text-[13px] sm:grid-cols-2">
          <div>
            <dt className="section-label !text-[9.5px]">What will happen</dt>
            <dd className="mt-1 text-ink-soft">{approval.what || approval.title}</dd>
          </div>
          <div>
            <dt className="section-label !text-[9.5px]">Why it&apos;s proposed</dt>
            <dd className="mt-1 text-ink-soft">{approval.why}</dd>
          </div>
          {!compact ? (
            <>
              <div>
                <dt className="section-label !text-[9.5px]">Target</dt>
                <dd className="mt-1 text-ink-soft">{approval.target}</dd>
              </div>
              <div>
                <dt className="section-label !text-[9.5px]">Reversibility</dt>
                <dd className="mt-1 text-ink-soft">
                  {approval.reversibility}
                  {approval.cost_estimate ? ` · cost ${approval.cost_estimate}` : ""}
                </dd>
              </div>
            </>
          ) : null}
        </dl>

        {!compact && approval.diff_preview ? (
          <div>
            <p className="section-label !text-[9.5px] mb-1.5">Before / after preview</p>
            <DiffWell diff={approval.diff_preview} />
          </div>
        ) : null}

        {!compact ? (
          <details className="text-[12.5px]">
            <summary className="cursor-pointer text-muted hover:text-ink">
              Technical details — exact data to be sent
            </summary>
            <pre className="mt-1.5 max-h-40 overflow-auto rounded-[9px] border border-line-row bg-well p-3.5 font-mono text-[11.5px]">
              {JSON.stringify(approval.data_preview, null, 2)}
            </pre>
          </details>
        ) : null}

        {pending ? (
          <div className="space-y-2.5 border-t border-line-row pt-3">
            {approval.confirm_phrase_required ? (
              <div>
                <p className="mb-1 text-[13px] font-medium text-danger">
                  High-impact action — type “{CONFIRM_PHRASE}” to enable Approve:
                </p>
                <Input
                  value={confirmPhrase}
                  onChange={(e) => setConfirmPhrase(e.target.value)}
                  aria-label="Confirmation phrase"
                />
              </div>
            ) : null}
            {!compact ? (
              <Input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Optional note (recorded in the audit trail)"
                aria-label="Decision note"
              />
            ) : null}
            {error ? <ErrorState title="Could not resolve" detail={error} /> : null}
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="primary"
                data-testid="approve-btn"
                busy={resolve.isPending}
                disabled={approveBlocked}
                onClick={() => resolve.mutate("approve")}
              >
                Approve once
              </Button>
              {onModify ? (
                <Button variant="secondary" onClick={onModify}>
                  Modify
                </Button>
              ) : null}
              <Button
                variant="danger"
                data-testid="deny-btn"
                busy={resolve.isPending}
                onClick={() => resolve.mutate("deny")}
              >
                Deny
              </Button>
              <Button variant="ghost" busy={cancelRun.isPending} onClick={() => cancelRun.mutate()}>
                Cancel the run
              </Button>
            </div>
            <p className="text-[11.5px] text-muted">
              “Always allow” rules live in Settings → Policies — never one click away from here.
            </p>
          </div>
        ) : approval.decision_note ? (
          <p className="border-t border-line-row pt-2 text-[12.5px] text-muted">
            Note: {approval.decision_note}
          </p>
        ) : null}
      </div>
    </div>
  );
}
