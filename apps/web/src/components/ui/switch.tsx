"use client";

import { cn } from "@/lib/utils";

// OttoOS spec §03: 38×21 pill, ivory knob, gold when on. 200ms toggle, color-only hover.
export function Switch({
  checked,
  onChange,
  label,
  disabled,
  tone = "accent",
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string; // always provide an accessible name
  disabled?: boolean;
  tone?: "accent" | "danger";
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-[21px] w-[38px] shrink-0 items-center rounded-full border transition-colors duration-200",
        checked
          ? tone === "danger"
            ? "bg-danger border-danger"
            : "bg-accent border-accent"
          : "bg-line-control border-line-control",
        disabled && "opacity-50 pointer-events-none",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "inline-block size-4 translate-x-[2px] rounded-full bg-ink shadow transition-transform duration-200",
          checked && "translate-x-[18px]",
        )}
      />
    </button>
  );
}
