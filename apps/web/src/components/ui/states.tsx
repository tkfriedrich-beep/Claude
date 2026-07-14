import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-lg bg-line/60", className)} />;
}

export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="rounded-[16px] border border-line-card bg-surface p-6 space-y-3" role="status" aria-label="Loading">
      <Skeleton className="h-4 w-1/3" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="h-3 w-full" />
      ))}
    </div>
  );
}

// Empty states speak in Otto's voice (Newsreader italic) — action-forward, never blank.
export function EmptyState({
  icon,
  title,
  hint,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-[16px] border border-dashed border-line-control bg-surface/60 px-6 py-12 text-center">
      {icon ? <div className="text-faint [&_svg]:size-7">{icon}</div> : null}
      <p className="otto-voice text-[17px] text-ink-soft">{title}</p>
      {hint ? <p className="max-w-sm text-[13px] text-muted">{hint}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  detail,
  onRetry,
}: {
  title?: string;
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="rounded-[16px] border border-danger/30 bg-danger-soft/60 px-5 py-4"
    >
      <p className="text-sm font-semibold text-danger">{title}</p>
      {detail ? (
        <details className="mt-1 text-[13px] text-ink/80">
          <summary className="cursor-pointer text-muted">Technical details</summary>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-xs">{detail}</pre>
        </details>
      ) : null}
      {onRetry ? (
        <Button size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-line-control bg-raised px-1.5 py-0.5 font-mono text-[11px] text-muted">
      {children}
    </kbd>
  );
}

// Mono section label (spec §01) — 10.5px uppercase, wide tracking.
export function SectionLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("section-label", className)}>{children}</div>;
}
