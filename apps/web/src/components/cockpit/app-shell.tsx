"use client";

// OttoOS shell (spec §04/§05): four zones with one job each — nav = places (grouped
// OPERATE / CONTEXT / SYSTEM, executive labels, routes unchanged), band = intent,
// workspace = the work, rail = periphery. Trust strip closes every screen. Work modes
// collapse zones around attention; mobile keeps the five bottom tabs.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Calendar, CheckSquare, Home, MessageSquare, MoreHorizontal, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";
import { ActivityRail } from "@/components/cockpit/activity-rail";
import { CommandBand, SafeModePill, TrustStrip } from "@/components/cockpit/command-band";
import { CommandPalette } from "@/components/cockpit/command-palette";
import { ThemeToggle, applyTheme } from "@/components/cockpit/theme-toggle";
import { useWorkMode, WorkModeProvider } from "@/components/cockpit/work-mode";
import { Kbd } from "@/components/ui/states";

// Executive labels over unchanged routes (spec §04 renames, 1:1).
const NAV_OPERATE = [
  { href: "/", label: "Briefing" },
  { href: "/command", label: "Command" },
  { href: "/projects", label: "Missions" },
  { href: "/skills", label: "Agents" },
  { href: "/approvals", label: "Decisions" },
];
const NAV_CONTEXT = [
  { href: "/agenda", label: "Calendar" },
  { href: "/people", label: "Relationships" },
  { href: "/knowledge", label: "Knowledge" },
];
const NAV_SYSTEM = [
  { href: "/automations", label: "Automations" },
  { href: "/integrations", label: "Systems" },
  { href: "/history", label: "Archive" },
  { href: "/settings", label: "Settings" },
];

const MOBILE_TABS = [
  { href: "/", label: "Briefing", icon: Home },
  { href: "/command", label: "Command", icon: MessageSquare },
  { href: "/approvals", label: "Decisions", icon: CheckSquare },
  { href: "/agenda", label: "Calendar", icon: Calendar },
];
// Everything not on the four bottom tabs — reachable on a phone via the "More" system sheet so
// Settings (and the rest of the roster) is one tap from every viewport (F3).
const MORE_DESTINATIONS = [
  { href: "/projects", label: "Missions" },
  { href: "/skills", label: "Agents" },
  { href: "/people", label: "Relationships" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/automations", label: "Automations" },
  { href: "/integrations", label: "Systems" },
  { href: "/history", label: "Archive" },
  { href: "/settings", label: "Settings" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <WorkModeProvider>
      <ShellInner>{children}</ShellInner>
    </WorkModeProvider>
  );
}

function ShellInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { mode } = useWorkMode();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

  const { data: onboarding, isLoading } = useQuery({
    queryKey: ["onboarding"],
    queryFn: api.onboardingStatus,
    retry: 1,
  });
  const { data: approvals } = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => api.approvals("pending"),
    enabled: onboarding?.completed === true,
    refetchInterval: 30_000,
  });
  const { data: settings } = useQuery({
    queryKey: ["settings"],
    queryFn: api.settings,
    enabled: onboarding?.completed === true,
  });
  const toggleSafe = useMutation({
    mutationFn: () => api.patchSettings({ safe_mode: !settings?.safe_mode }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["briefing"] });
    },
  });

  useEffect(() => {
    applyTheme(localStorage.getItem("cockpit-theme") ?? "dark");
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Onboarding gate: everything except /onboarding redirects until completed.
  useEffect(() => {
    if (!isLoading && onboarding && !onboarding.completed && pathname !== "/onboarding") {
      router.replace("/onboarding");
    }
  }, [isLoading, onboarding, pathname, router]);

  // Close the mobile system menu on any route change.
  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  if (pathname === "/onboarding") {
    return <>{children}</>;
  }

  const pendingCount = approvals?.length ?? 0;
  const navHidden = mode !== "command";
  const initials = (onboarding?.user_name ?? "?")
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const renderGroup = (label: string, items: { href: string; label: string }[]) => (
    <div key={label}>
      <div className="section-label px-2.5 pb-1.5 pt-4">{label}</div>
      <ul className="space-y-0.5">
        {items.map(({ href, label: itemLabel }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-2.5 rounded-[9px] px-2.5 py-2 text-[14px]",
                  active
                    ? "bg-accent-soft font-medium text-accent-hover shadow-[inset_2px_0_0_var(--accent)]"
                    : "text-muted-2 hover:text-ink",
                )}
              >
                <span className="flex-1">{itemLabel}</span>
                {href === "/approvals" && pendingCount > 0 ? (
                  <span
                    data-testid="nav-approvals-badge"
                    className="rounded-full border border-(--warn-border) bg-warn-soft px-2 py-px font-mono text-[11px] font-medium text-warn"
                  >
                    {pendingCount}
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );

  return (
    <div className="flex min-h-dvh">
      {/* left nav — collapses in focus/deep (spec §05) */}
      <nav
        aria-label="Primary"
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col overflow-y-auto border-r border-line bg-nav px-3 py-5",
          "transition-[width,opacity,padding] duration-300",
          navHidden ? "lg:flex lg:w-0 lg:overflow-hidden lg:px-0 lg:opacity-0" : "lg:flex lg:w-[232px]",
        )}
      >
        <Link href="/" className="flex items-center gap-3 px-2.5 pb-3">
          <span
            aria-hidden
            className="size-8 shrink-0 rounded-full shadow-[0_0_0_1px_var(--accent-border)]"
            style={{
              background:
                "radial-gradient(circle at 35% 30%, #f0d9a4, #c9a961 45%, #8a713c 78%, #4a3d22)",
            }}
          />
          <span>
            <span className="block text-[18px] font-semibold leading-none tracking-[-0.01em]">
              OttoOS
            </span>
            <span className="mt-1 block font-mono text-[9.5px] tracking-[0.16em] text-muted-2">
              LOCAL-FIRST
            </span>
          </span>
        </Link>
        {renderGroup("Operate", NAV_OPERATE)}
        {renderGroup("Context", NAV_CONTEXT)}
        {renderGroup("System", NAV_SYSTEM)}
        <div className="mt-auto space-y-3 px-2.5 pt-5">
          <SafeModePill
            settings={settings}
            isPending={toggleSafe.isPending}
            onToggle={() => toggleSafe.mutate()}
            testid="safe-mode-pill"
          />
          <div className="flex items-center gap-2.5 border-t border-line pt-3.5">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-line-button font-mono text-[11px] text-ink-soft">
              {initials}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-medium leading-tight">
                {onboarding?.user_name ?? "—"}
              </span>
              <span className="block text-[11px] text-muted-2">Principal</span>
            </span>
          </div>
          <div className="flex items-center justify-between pt-1">
            <button
              onClick={() => setPaletteOpen(true)}
              className="flex items-center gap-1.5 text-xs text-muted hover:text-ink"
            >
              <Kbd>⌘K</Kbd> palette
            </button>
            <ThemeToggle />
          </div>
        </div>
      </nav>

      {/* center column: command band · workspace · trust strip */}
      <div className="flex min-h-dvh min-w-0 flex-1 flex-col">
        <CommandBand />
        <main
          className={cn(
            "min-w-0 flex-1 px-4 pb-24 pt-6 sm:px-7 lg:pb-10",
            mode === "deep" && "mx-auto w-full max-w-[1720px]",
          )}
        >
          {children}
        </main>
        <TrustStrip />
      </div>

      {/* right ambient rail (desktop ≥ xl; toggleable drawer below; collapses in Deep Work) */}
      <ActivityRail open={railOpen} onToggle={() => setRailOpen((o) => !o)} />

      {/* mobile bottom tabs — four primary + a "More" system menu */}
      <nav
        aria-label="Primary mobile"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-nav/95 px-1 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        {MOBILE_TABS.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-[52px] flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[11px]",
                active ? "text-accent-hover" : "text-muted",
              )}
            >
              <span className="relative">
                <Icon className="size-5" />
                {href === "/approvals" && pendingCount > 0 ? (
                  <span className="absolute -right-2 -top-1 flex size-4 items-center justify-center rounded-full bg-warn text-[9px] font-bold text-on-accent">
                    {pendingCount}
                  </span>
                ) : null}
              </span>
              {label}
            </Link>
          );
        })}
        <button
          type="button"
          onClick={() => setMoreOpen((o) => !o)}
          aria-expanded={moreOpen}
          className={cn(
            "flex min-h-[52px] flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[11px]",
            moreOpen || MORE_DESTINATIONS.some((d) => pathname === d.href)
              ? "text-accent-hover"
              : "text-muted",
          )}
        >
          <MoreHorizontal className="size-5" />
          More
        </button>
      </nav>

      {/* mobile system menu — Settings, Systems, Automations, and the rest of the roster (F3) */}
      {moreOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="System menu">
          <button
            aria-label="Close system menu"
            tabIndex={-1}
            className="absolute inset-0 bg-black/50"
            onClick={() => setMoreOpen(false)}
          />
          <div className="absolute inset-x-0 bottom-0 rounded-t-[16px] border-t border-line bg-surface px-4 pb-[calc(env(safe-area-inset-bottom)+72px)] pt-4 shadow-[0_-16px_40px_rgba(0,0,0,.4)]">
            <div className="flex items-center justify-between">
              <span className="section-label">System menu</span>
              <button aria-label="Close system menu" onClick={() => setMoreOpen(false)} className="text-muted">
                <X className="size-4" />
              </button>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {MORE_DESTINATIONS.map(({ href, label }) => (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setMoreOpen(false)}
                  className="rounded-[11px] border border-line-row bg-tile px-4 py-3 text-[14px] font-medium text-ink-soft hover:text-ink"
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      {/* activity toggle for < xl screens */}
      <button
        onClick={() => setRailOpen((o) => !o)}
        aria-label="Toggle activity rail"
        className="fixed bottom-20 right-4 z-40 rounded-full border border-line bg-raised p-3 shadow-lg lg:bottom-6 xl:hidden"
      >
        <Activity className="size-4.5 text-accent" />
      </button>
    </div>
  );
}
