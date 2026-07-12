import { cn } from "@/lib/utils";

type Tone = "accent" | "warn" | "danger" | "muted" | "outline";

const tones: Record<Tone, string> = {
  accent: "bg-accent-soft text-accent",
  warn: "bg-warn-soft text-warn",
  danger: "bg-danger-soft text-danger",
  muted: "bg-line/50 text-muted",
  outline: "border border-line text-muted bg-transparent",
};

export function Badge({
  tone = "muted",
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11.5px] font-medium",
        "whitespace-nowrap leading-4",
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}

export function RiskBadge({ risk }: { risk: string }) {
  const tone = risk === "R4" ? "danger" : risk === "R3" ? "warn" : risk === "R2" ? "accent" : "muted";
  const label: Record<string, string> = {
    R0: "R0 · local read",
    R1: "R1 · external read",
    R2: "R2 · local write",
    R3: "R3 · external write",
    R4: "R4 · high impact",
  };
  return <Badge tone={tone}>{label[risk] ?? risk}</Badge>;
}
