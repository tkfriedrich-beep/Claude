"use client";

// Cmd/Ctrl+K palette: navigate, run skills, toggle Safe Mode. Power path, never required.
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createPortal } from "react-dom";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Layers, Moon, Navigation, Play, Shield } from "lucide-react";
import { applyTheme } from "@/components/cockpit/theme-toggle";

interface PaletteAction {
  id: string;
  label: string;
  hint?: string;
  icon: React.ReactNode;
  run: () => void | Promise<void>;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: skills } = useQuery({ queryKey: ["skills"], queryFn: api.skills, enabled: open });
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: open });
  const runSkill = useMutation({
    mutationFn: (slug: string) => api.runSkill(slug),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      router.push(`/history/${run.id}`);
    },
  });

  const actions = useMemo<PaletteAction[]>(() => {
    const nav: PaletteAction[] = [
      "/", "/command", "/skills", "/approvals", "/automations", "/integrations",
      "/history", "/agenda", "/projects", "/people", "/knowledge", "/settings",
    ].map((href) => ({
      id: `nav:${href}`,
      label: `Go to ${href === "/" ? "Home" : href.slice(1).replace(/^./, (c) => c.toUpperCase())}`,
      icon: <Navigation className="size-4" />,
      run: () => router.push(href),
    }));
    const skillActions: PaletteAction[] = (skills ?? []).map((skill) => ({
      id: `skill:${skill.slug}`,
      label: `Run ${skill.name}`,
      hint: skill.risk_level,
      icon: <Play className="size-4" />,
      run: async () => {
        await runSkill.mutateAsync(skill.slug);
      },
    }));
    const toggles: PaletteAction[] = [
      {
        id: "safe-mode",
        label: settings?.safe_mode ? "Turn Safe Mode OFF (allow external writes)" : "Turn Safe Mode ON",
        icon: <Shield className="size-4" />,
        run: async () => {
          await api.patchSettings({ safe_mode: !settings?.safe_mode });
          queryClient.invalidateQueries({ queryKey: ["settings"] });
          queryClient.invalidateQueries({ queryKey: ["briefing"] });
        },
      },
      {
        id: "theme",
        label: "Toggle dark/light theme",
        icon: <Moon className="size-4" />,
        run: () => {
          const isDark = document.documentElement.dataset.theme === "dark";
          applyTheme(isDark ? "light" : "dark");
        },
      },
    ];
    return [...skillActions, ...nav, ...toggles];
  }, [skills, settings, router, queryClient, runSkill]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return actions.slice(0, 12);
    return actions.filter((a) => a.label.toLowerCase().includes(q)).slice(0, 12);
  }, [actions, query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [open]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12dvh]">
      <button aria-label="Close palette" tabIndex={-1} className="absolute inset-0 bg-ink/30" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="relative w-full max-w-lg overflow-hidden rounded-[14px] border border-line bg-surface shadow-2xl"
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIndex(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setIndex((i) => Math.min(i + 1, filtered.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setIndex((i) => Math.max(i - 1, 0)); }
            if (e.key === "Enter" && filtered[index]) {
              filtered[index].run();
              onClose();
            }
            if (e.key === "Escape") onClose();
          }}
          placeholder="Run a skill, jump somewhere, toggle Safe Mode…"
          aria-label="Palette search"
          className="w-full border-b border-line bg-transparent px-4 py-3.5 text-sm outline-none"
        />
        <ul className="max-h-[45dvh] overflow-y-auto p-1.5" role="listbox">
          {filtered.length === 0 ? (
            <li className="px-3 py-4 text-sm text-muted">Nothing matches “{query}”.</li>
          ) : (
            filtered.map((action, i) => (
              <li key={action.id} role="option" aria-selected={i === index}>
                <button
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-[10px] px-3 py-2.5 text-left text-sm",
                    i === index ? "bg-accent-soft text-accent" : "hover:bg-line/40",
                  )}
                  onMouseEnter={() => setIndex(i)}
                  onClick={() => {
                    action.run();
                    onClose();
                  }}
                >
                  <span className="text-muted">{action.icon}</span>
                  <span className="flex-1">{action.label}</span>
                  {action.hint ? <span className="font-mono text-[11px] text-muted">{action.hint}</span> : null}
                </button>
              </li>
            ))
          )}
        </ul>
        <div className="flex items-center gap-3 border-t border-line px-4 py-2 text-[11px] text-muted">
          <span>↑↓ navigate</span>
          <span>↵ run</span>
          <span>esc close</span>
          <Layers className="ml-auto size-3.5" />
        </div>
      </div>
    </div>,
    document.body,
  );
}
