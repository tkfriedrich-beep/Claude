"use client";

// The approval card shows, in plain language: what, why, target, data, preview,
// risk & reversibility, cost — approve once / deny / cancel run. "Always allow"
// deliberately does NOT exist here (policy editor only, per BUILD_BRIEF).
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Approval } from "@/lib/types";
import { timeAgo } from "@/lib/utils";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/states";

const CONFIRM_PHRASE = "I understand the risk";

export function ApprovalCard({ approval, compact }: { approval: Approval; compact?: boolean }) {
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

  return (
    <Card data-testid="approval-card" className={pending ? "border-warn/50" : undefined}>
      <div className="space-y-3 p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="text-[15px] font-semibold leading-snug">{approval.title}</h3>
            <p className="mt-0.5 text-[12.5px] text-muted">
              requested {timeAgo(approval.requested_at)}
              {approval.expires_at && pending ? <> · expires {timeAgo(approval.expires_at).replace(" ago", "")}</> : null}
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            <RiskBadge risk={approval.risk_level} />
            {!pending ? (
              <Badge tone={approval.status === "approved" ? "accent" : approval.status === "denied" ? "danger" : "muted"}>
                {approval.status}
              </Badge>
            ) : null}
          </div>
        </div>

        <dl className="grid gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-2">
          <div>
            <dt className="font-medium text-muted">What will happen</dt>
            <dd>{approval.what || approval.title}</dd>
          </div>
          <div>
            <dt className="font-medium text-muted">Why it&apos;s proposed</dt>
            <dd>{approval.why}</dd>
          </div>
          <div>
            <dt className="font-medium text-muted">Target</dt>
            <dd>{approval.target}</dd>
          </div>
          <div>
            <dt className="font-medium text-muted">Reversibility</dt>
            <dd>{approval.reversibility}{approval.cost_estimate ? ` · cost ${approval.cost_estimate}` : ""}</dd>
          </div>
        </dl>

        {approval.diff_preview ? (
          <div>
            <p className="mb-1 text-[12.5px] font-medium text-muted">Before / after preview</p>
            <pre className="max-h-56 overflow-auto rounded-[10px] border border-line bg-raised p-3 font-mono text-[11.5px] leading-relaxed">
              {approval.diff_preview}
            </pre>
          </div>
        ) : null}

        <details className="text-[12.5px]">
          <summary className="cursor-pointer text-muted hover:text-ink">
            Technical details — exact data to be sent
          </summary>
          <pre className="mt-1.5 max-h-40 overflow-auto rounded-[10px] border border-line bg-raised p-3 font-mono text-[11.5px]">
            {JSON.stringify(approval.data_preview, null, 2)}
          </pre>
        </details>

        {pending ? (
          <div className="space-y-2.5 border-t border-line pt-3">
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
            <div className="flex flex-wrap gap-2">
              <Button
                variant="primary"
                data-testid="approve-btn"
                busy={resolve.isPending}
                disabled={approval.confirm_phrase_required && confirmPhrase.trim() !== CONFIRM_PHRASE}
                onClick={() => resolve.mutate("approve")}
              >
                Approve once
              </Button>
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
          <p className="border-t border-line pt-2 text-[12.5px] text-muted">
            Note: {approval.decision_note}
          </p>
        ) : null}
      </div>
    </Card>
  );
}
