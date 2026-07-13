"use client";

// ⌘K universal command (OttoOS spec §05): GO TO (12 destinations) · RUN (agents) ·
// CONTROL (Safe Mode, theme) · MODE (Focus / Deep Work) — filterable, never required.
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createPortal } from "react-dom";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { agentMetaFor } from "@/components/ui/monogram";
import { applyTheme } from "@/components/cockpit/theme-toggle";
import { useWorkMode } from "@/components/cockpit/work-mode";

interface PaletteAction {
  id: string;
  kind: "GO TO" | "RUN" | "CONTROL" | "MODE";
  label: string;
  hint?: string;
  run: () => void | Promise<void>;
}

const DESTINATIONS: { href: string; label: string }[] = [
  { href: "/", label: "Briefing" },
  { href: "/command", label: "Command" },
  { href: "/projects", label: "Missions" },
  { href: "/skills", label: "Agents" },
  { href: "/approvals", label: "Decisions" },
  { href: "/agenda", label: "Calendar" },
  { href: "/people", label: "Relationships" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/automations", label: "Automations" },
  { href: "/integrations", label: "Systems" },
  { href: "/history", label: "Archive" },
  { href: "/settings", label: "Settings" },
];

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { setMode } = useWorkMode();
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
    const nav: PaletteAction[] = DESTINATIONS.map(({ href, label }) => ({
      id: `nav:${href}`,
      kind: "GO TO",
      label,
      run: () => router.push(href),
    }));
    const agents: PaletteAction[] = (skills ?? []).map((skill) => {
      const meta = agentMetaFor(skill.slug, skill.name);
      return {
        id: `skill:${skill.slug}`,
        kind: "RUN" as const,
        label: `${meta.name} — ${skill.name}`,
        hint: skill.risk_level,
        run: async () => {
          await runSkill.mutateAsync(skill.slug);
        },
      };
    });
    const control: PaletteAction[] = [
      {
        id: "safe-mode",
        kind: "CONTROL",
        label: settings?.safe_mode
          ? "Turn Safe Mode OFF (allow external writes)"
          : "Turn Safe Mode ON",
        run: async () => {
          await api.patchSettings({ safe_mode: !settings?.safe_mode });
          queryClient.invalidateQueries({ queryKey: ["settings"] });
          queryClient.invalidateQueries({ queryKey: ["briefing"] });
        },
      },
      {
        id: "theme",
        kind: "CONTROL",
        label: "Toggle midnight / parchment theme",
        run: () => {
          const isDark = document.documentElement.dataset.theme === "dark";
          applyTheme(isDark ? "light" : "dark");
        },
      },
    ];
    const modes: PaletteAction[] = [
      { id: "mode:deep", kind: "MODE", label: "Enter Deep Work", hint: "ESC exits", run: () => setMode("deep") },
      { id: "mode:focus", kind: "MODE", label: "Enter Focus", hint: "nav collapses", run: () => setMode("focus") },
      { id: "mode:command", kind: "MODE", label: "Back to Command", run: () => setMode("command") },
    ];
    return [...nav, ...agents, ...control, ...modes];
  }, [skills, settings, router, queryClient, runSkill, setMode]);

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return actions.slice(0, 14);
    return actions
      .filter((a) => a.label.toLowerCase().includes(q) || a.kind.toLowerCase().includes(q))
      .slice(0, 14);
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
      <button aria-label="Close palette" tabIndex={-1} className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="relative w-full max-w-xl overflow-hidden rounded-[16px] border border-line-button bg-surface shadow-[0_24px_80px_rgba(0,0,0,.6)]"
      >
        <div className="flex items-center gap-3 border-b border-line-card px-5 py-3.5">
          <span className="font-mono text-[12px] font-medium text-accent">⌘K</span>
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
            placeholder="Go to, run an agent, toggle a control…"
            aria-label="Palette search"
            className="flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted/70"
          />
          <span className="font-mono text-[11px] text-faint">ESC</span>
        </div>
        <ul className="max-h-[46dvh] overflow-y-auto p-2" role="listbox">
          {filtered.length === 0 ? (
            <li className="otto-voice px-3 py-4 text-[15px] text-muted">Nothing matches “{query}”.</li>
          ) : (
            filtered.map((action, i) => (
              <li key={action.id} role="option" aria-selected={i === index}>
                <button
                  className={cn(
                    "flex w-full items-center gap-3 rounded-[9px] px-3.5 py-2.5 text-left text-sm",
                    i === index ? "bg-accent-soft text-ink" : "text-ink-soft hover:bg-accent-soft/50",
                  )}
                  onMouseEnter={() => setIndex(i)}
                  onClick={() => {
                    action.run();
                    onClose();
                  }}
                >
                  <span className="w-16 shrink-0 font-mono text-[10.5px] tracking-[0.08em] text-faint">
                    {action.kind}
                  </span>
                  <span className="flex-1">{action.label}</span>
                  {action.hint ? (
                    <span className="font-mono text-[11px] text-faint">{action.hint}</span>
                  ) : null}
                </button>
              </li>
            ))
          )}
        </ul>
        <div className="flex items-center gap-3 border-t border-line-card px-5 py-2 text-[11px] text-faint">
          <span>↑↓ navigate</span>
          <span>↵ run</span>
          <span>esc close</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
