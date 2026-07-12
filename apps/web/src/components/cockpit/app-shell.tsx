"use client";

// Three-zone desktop layout (left nav / workspace / activity rail), bottom
// tab bar on mobile (capture, briefing, approvals — no desktop admin cramming).
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  Calendar,
  CheckSquare,
  Clock,
  FolderKanban,
  Home,
  Layers,
  Library,
  MessageSquare,
  Plug,
  Repeat,
  Settings,
  Users,
} from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";
import { ActivityRail } from "@/components/cockpit/activity-rail";
import { CommandPalette } from "@/components/cockpit/command-palette";
import { ThemeToggle, applyTheme } from "@/components/cockpit/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Kbd } from "@/components/ui/states";

const NAV = [
  { href: "/", label: "Home", icon: Home },
  { href: "/command", label: "Command", icon: MessageSquare },
  { href: "/agenda", label: "Agenda", icon: Calendar },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/people", label: "People", icon: Users },
  { href: "/knowledge", label: "Knowledge", icon: Library },
  { href: "/skills", label: "Skills", icon: Layers },
  { href: "/automations", label: "Automations", icon: Repeat },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/approvals", label: "Approvals", icon: CheckSquare },
  { href: "/history", label: "History", icon: Clock },
  { href: "/settings", label: "Settings", icon: Settings },
];

const MOBILE_NAV = [
  { href: "/", label: "Home", icon: Home },
  { href: "/command", label: "Command", icon: MessageSquare },
  { href: "/approvals", label: "Approvals", icon: CheckSquare },
  { href: "/agenda", label: "Agenda", icon: Calendar },
  { href: "/history", label: "More", icon: Clock },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(false);

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

  useEffect(() => {
    applyTheme(localStorage.getItem("cockpit-theme") ?? "system");
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

  if (pathname === "/onboarding") {
    return <>{children}</>;
  }

  const pendingCount = approvals?.length ?? 0;

  return (
    <div className="flex min-h-dvh">
      {/* left nav */}
      <nav
        aria-label="Primary"
        className="sticky top-0 hidden h-dvh w-[212px] shrink-0 flex-col border-r border-line bg-surface/70 px-3 py-4 lg:flex"
      >
        <Link href="/" className="mb-5 flex items-center gap-2.5 px-2">
          <span className="flex size-8 items-center justify-center rounded-[10px] bg-accent text-white">
            <Bot className="size-4.5" />
          </span>
          <span className="text-[15px] font-semibold tracking-tight">AgenticOS</span>
        </Link>
        <ul className="space-y-0.5">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || (href !== "/" && pathname.startsWith(href));
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2.5 rounded-[10px] px-2.5 py-2 text-[13.5px] font-medium",
                    active
                      ? "bg-accent-soft text-accent"
                      : "text-muted hover:bg-line/40 hover:text-ink",
                  )}
                >
                  <Icon className="size-4" />
                  <span className="flex-1">{label}</span>
                  {href === "/approvals" && pendingCount > 0 ? (
                    <Badge tone="warn" data-testid="nav-approvals-badge">{pendingCount}</Badge>
                  ) : null}
                </Link>
              </li>
            );
          })}
        </ul>
        <div className="mt-auto flex items-center justify-between px-2 pt-4">
          <button
            onClick={() => setPaletteOpen(true)}
            className="flex items-center gap-1.5 text-xs text-muted hover:text-ink"
          >
            <Kbd>⌘K</Kbd> palette
          </button>
          <ThemeToggle />
        </div>
      </nav>

      {/* workspace */}
      <main className="min-w-0 flex-1 px-4 pb-24 pt-5 sm:px-6 lg:px-8 lg:pb-8">{children}</main>

      {/* right activity rail (desktop ≥ xl; toggleable drawer below) */}
      <ActivityRail open={railOpen} onToggle={() => setRailOpen((o) => !o)} />

      {/* mobile bottom tabs */}
      <nav
        aria-label="Primary mobile"
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-surface/95 backdrop-blur px-1 pb-[env(safe-area-inset-bottom)] lg:hidden"
      >
        {MOBILE_NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex min-h-[52px] flex-1 flex-col items-center justify-center gap-0.5 py-1.5 text-[11px]",
                active ? "text-accent" : "text-muted",
              )}
            >
              <span className="relative">
                <Icon className="size-5" />
                {href === "/approvals" && pendingCount > 0 ? (
                  <span className="absolute -right-2 -top-1 flex size-4 items-center justify-center rounded-full bg-warn text-[9px] font-bold text-white">
                    {pendingCount}
                  </span>
                ) : null}
              </span>
              {label}
            </Link>
          );
        })}
      </nav>

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
