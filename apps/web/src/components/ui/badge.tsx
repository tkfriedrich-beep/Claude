import { cn } from "@/lib/utils";

type Tone = "accent" | "warn" | "danger" | "muted" | "outline" | "ok";

// OttoOS spec §03: chips are hairline-bordered mono pills. Amber appears ONLY when
// human judgment is required (pending decisions, attention, shadow, degraded).
const tones: Record<Tone, string> = {
  accent: "text-accent-hover border border-(--accent-border) bg-transparent",
  warn: "text-warn border border-(--warn-border) bg-warn-soft",
  danger: "text-danger border border-danger/40 bg-transparent",
  muted: "text-muted-2 border border-line-control bg-transparent",
  outline: "border border-line-control text-muted-2 bg-transparent",
  ok: "text-ok border border-ok/40 bg-transparent",
};

export function Badge({
  tone = "muted",
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-[3px] font-mono text-[10.5px] font-medium",
        "whitespace-nowrap leading-4 tracking-[0.06em] uppercase",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}

// Risk ladder chips (spec §03): R0/R1 neutral · R2 gold (reversible local writes) ·
// R3 amber (external — judgment) · R4 danger.
export function RiskBadge({ risk }: { risk: string }) {
  const tone: Tone =
    risk === "R4" ? "danger" : risk === "R3" ? "warn" : risk === "R2" ? "accent" : "muted";
  const label: Record<string, string> = {
    R0: "R0 · local read",
    R1: "R1 · external read",
    R2: "R2 · local write",
    R3: "R3 · external write",
    R4: "R4 · high impact",
  };
  return <Badge tone={tone}>{label[risk] ?? risk}</Badge>;
}
