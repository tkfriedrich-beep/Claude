"use client";

import { cn } from "@/lib/utils";

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
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors",
        checked
          ? tone === "danger"
            ? "bg-danger border-danger"
            : "bg-accent border-accent"
          : "bg-line border-line",
        disabled && "opacity-50 pointer-events-none",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "inline-block size-4.5 translate-x-0.5 rounded-full bg-white shadow transition-transform",
          checked && "translate-x-[22px]",
        )}
      />
    </button>
  );
}
