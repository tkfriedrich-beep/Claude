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
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const saved = localStorage.getItem("cockpit-theme") ?? "system";
    setTheme(saved);
    applyTheme(saved);
  }, []);

  // Reflect the DOM-resolved theme only AFTER mount. The pre-hydration theme script in layout
  // already set data-theme on <html> (e.g. "dark") before React hydrates, but the server rendered
  // the light default — reading the DOM during the first client render would make the icon +
  // aria-label differ from the server HTML and trip a hydration mismatch. Gating on `mounted`
  // keeps the server render and first client render identical; the real theme lands one tick later.
  const isDark =
    mounted &&
    typeof document !== "undefined" &&
    document.documentElement.dataset.theme === "dark";

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
