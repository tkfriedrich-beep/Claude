"use client";

import { cn } from "@/lib/utils";

// OttoOS spec §03: segmented control — hairline-bordered strip, gold-soft selected cell.
// Used for autonomy modes (Advise / Draft / Execute + approval / In-policy), tabs, filters.
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  size = "md",
  mono = false,
  label,
  className,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (next: T) => void;
  size?: "sm" | "md";
  mono?: boolean;
  label: string; // accessible name for the group
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn(
        "inline-flex overflow-hidden rounded-[9px] border border-line-control",
        className,
      )}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={cn(
              "whitespace-nowrap transition-colors duration-200",
              size === "sm" ? "px-3 py-[5px] text-[11.5px]" : "px-3.5 py-2 text-[12.5px]",
              mono && "font-mono tracking-[0.04em]",
              selected
                ? "bg-accent-soft font-medium text-accent-hover"
                : "text-muted-2 hover:text-accent-hover",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
