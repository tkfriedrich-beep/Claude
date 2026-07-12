"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

export function applyTheme(theme: string) {
  const resolved =
    theme === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : theme;
  document.documentElement.dataset.theme = resolved;
  try {
    localStorage.setItem("cockpit-theme", theme);
  } catch {
    /* private mode */
  }
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<string>("system");

  useEffect(() => {
    const saved = localStorage.getItem("cockpit-theme") ?? "system";
    setTheme(saved);
    applyTheme(saved);
  }, []);

  const isDark =
    typeof document !== "undefined" && document.documentElement.dataset.theme === "dark";

  return (
    <button
      onClick={() => {
        const next = isDark ? "light" : "dark";
        setTheme(next);
        applyTheme(next);
      }}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className="rounded-lg border border-line bg-raised p-2 text-muted hover:text-ink"
      data-theme-current={theme}
    >
      {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}
