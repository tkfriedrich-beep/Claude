import { cn } from "@/lib/utils";
import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "warn";
type Size = "sm" | "md" | "lg";

// OttoOS spec §03: primary = champagne gold on near-black; secondary = hairline outline;
// tertiary/destructive stay text-weight. Hover changes color/border only — never size.
const variants: Record<Variant, string> = {
  primary: "bg-accent text-on-accent hover:bg-accent-hover border-transparent font-semibold",
  secondary: "bg-transparent text-ink-soft border-line-button hover:border-faint hover:text-ink",
  ghost: "bg-transparent text-muted-2 border-transparent hover:text-ink hover:bg-accent-soft",
  danger: "bg-transparent text-danger border-transparent hover:text-danger-hover",
  warn: "bg-warn-soft text-warn border-(--warn-border) hover:brightness-110",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-11 px-5 text-[15px] gap-2",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  busy?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "secondary", size = "md", busy, disabled, children, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || busy}
      className={cn(
        "inline-flex items-center justify-center rounded-[9px] border font-medium",
        "transition-colors duration-150 select-none whitespace-nowrap",
        "disabled:opacity-50 disabled:pointer-events-none",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {busy ? (
        <span
          aria-hidden
          className="size-3.5 rounded-full border-2 border-current border-t-transparent animate-spin"
        />
      ) : null}
      {children}
    </button>
  );
});
