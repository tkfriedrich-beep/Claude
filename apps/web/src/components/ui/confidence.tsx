import { cn } from "@/lib/utils";

// OttoOS spec §03: confidence = mono two-decimal + word.
// HIGH ≥ .70 (gold-bright) · MED .40–.69 (amber, soft) · LOW < .40 (amber).
export function ConfidenceTag({ value, className }: { value: number; className?: string }) {
  const word = value >= 0.7 ? "HIGH" : value >= 0.4 ? "MED" : "LOW";
  const color = value >= 0.7 ? "text-accent-hover" : "text-warn";
  return (
    <span className={cn("font-mono text-[12px] font-medium text-muted-2", className)}>
      CONF <span className={color}>{value.toFixed(2)} {word}</span>
    </span>
  );
}

// 3px progress bar — gold; amber when the mission is flagged (spec §03).
export function ProgressBar({
  pct,
  flagged,
  className,
}: {
  pct: number;
  flagged?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("block h-[3px] rounded-[2px] bg-line-card", className)}>
      <span
        className={cn("block h-[3px] rounded-[2px]", flagged ? "bg-warn" : "bg-accent")}
        style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
      />
    </span>
  );
}
