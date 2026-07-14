"use client";

import { useRef } from "react";
import { cn } from "@/lib/utils";
import { handleRadioKeys } from "@/lib/a11y";

// OttoOS spec §03: segmented control — hairline-bordered strip, gold-soft selected cell.
// Used for autonomy modes (Advise / Draft / Execute), tabs, filters, theme.
// WAI-ARIA radio group: one tabbable checked item (roving tabIndex) + arrow/Home/End keys.
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
  const btns = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedIndex = options.findIndex((o) => o.value === value);

  // Move selection AND focus together (roving tabindex) — the WAI-ARIA radio pattern.
  const select = (index: number) => {
    const option = options[index];
    if (!option) return;
    onChange(option.value);
    btns.current[index]?.focus();
  };

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn(
        "inline-flex overflow-hidden rounded-[9px] border border-line-control",
        className,
      )}
    >
      {options.map((option, i) => {
        const selected = option.value === value;
        // Only the checked radio is tabbable; if none is checked, the first is (roving tabindex).
        const tabbable = selected || (selectedIndex === -1 && i === 0);
        return (
          <button
            key={option.value}
            ref={(el) => {
              btns.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={tabbable ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(e) => handleRadioKeys(e, options.length, selectedIndex, select)}
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
