import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

// OttoOS spec §01 geometry: card radius 16, hairlines carry depth — no shadows on cards.
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-[16px] border border-line-card bg-surface", className)}
      {...props}
    />
  );
}

export function CardHeader({
  title,
  action,
  subtitle,
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-3 px-6 pt-5 pb-2", className)}>
      <div className="min-w-0">
        <h2 className="text-[16.5px] font-semibold tracking-[-0.01em]">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-[13px] text-muted">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-6 pb-5", className)} {...props} />;
}
