"use client";

// The command band (OttoOS spec §04/§05): Otto hero + status, the persistent composer with
// execution-mode segments, and vitals (clock, budget, systems, work-mode). In Deep Work it
// slims to Otto-mini + an honest "interruptions hidden" line. The trust strip closes every
// screen. Trust surfaces never fabricate: missing state reads as "unavailable", never healthy.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SettingsResponse } from "@/lib/types";
import { ACTIVE_RUN_STATUSES, cn } from "@/lib/utils";
import { deriveOttoState, OTTO_STATUS, OttoPulse } from "@/components/cockpit/otto-pulse";
import { useWorkMode, type WorkMode } from "@/components/cockpit/work-mode";
import { SegmentedControl } from "@/components/ui/segmented";

// Execution-mode segments map 1:1 to the API's run modes (spec §03). There is deliberately no
// per-command "allowlist"/"in-policy" segment: whether an allow-listed tool runs without an
// approval is a property of the agent's persisted autonomy (level 5) plus Settings → Policies —
// a mode label must never silently raise effective autonomy.
const AUTONOMY = [
  { value: "read_only", label: "Advise" },
  { value: "draft", label: "Draft" },
  { value: "act", label: "Execute" },
] as const;
type Autonomy = (typeof AUTONOMY)[number]["value"];

const WORK_MODES: { value: WorkMode; label: string }[] = [
  { value: "command", label: "COMMAND" },
  { value: "focus", label: "FOCUS" },
  { value: "deep", label: "DEEP" },
];

export function useOttoStatus() {
  const { data: onboarding } = useQuery({ queryKey: ["onboarding"], queryFn: api.onboardingStatus });
  const enabled = onboarding?.completed === true;
  const runsQ = useQuery({
    queryKey: ["runs", "active"],
    queryFn: () => api.runs({ status: ACTIVE_RUN_STATUSES.join(",") }),
    enabled,
    refetchInterval: 15_000,
  });
  const pendingQ = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => api.approvals("pending"),
    enabled,
    refetchInterval: 30_000,
  });
  const state = deriveOttoState(runsQ.data ?? [], pendingQ.data?.length ?? 0);
  // "Steady" must reflect a real read, not a failed one — surface outages explicitly (F6).
  const unavailable = enabled && (runsQ.isError || pendingQ.isError);
  return {
    state,
    activeRuns: runsQ.data ?? [],
    pending: pendingQ.data ?? [],
    enabled,
    unavailable,
  };
}

function useClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(t);
  }, []);
  return now;
}

// One Safe Mode control, honest about unknown state — shared by the desktop nav and the mobile
// band so the emergency gate is one tap from every viewport (F3) and never fabricates (F6).
export function SafeModePill({
  settings,
  isPending,
  onToggle,
  testid,
  className,
}: {
  settings: SettingsResponse | undefined; // undefined = not yet known (loading or error)
  isPending: boolean;
  onToggle: () => void;
  testid: string;
  className?: string;
}) {
  const known = settings !== undefined;
  const safeOn = settings?.safe_mode === true;
  return (
    <button
      onClick={onToggle}
      data-testid={testid}
      disabled={!known || isPending}
      aria-label={
        known
          ? safeOn
            ? "Safe Mode on — external writes blocked"
            : "Safe Mode off"
          : "Safe Mode status unavailable"
      }
      className={cn(
        "flex w-fit items-center gap-2 rounded-full border px-3 py-1.5 font-mono text-[10.5px] font-medium tracking-[0.06em] disabled:opacity-70",
        !known
          ? "border-line-control text-muted-2"
          : safeOn
            ? "border-(--accent-border) text-accent-hover"
            : "border-(--warn-border) text-warn",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn("size-[7px] rounded-full", !known ? "bg-faint" : safeOn ? "bg-accent" : "bg-warn")}
      />
      {!known ? "Safe Mode —" : safeOn ? "Safe Mode on" : "Safe Mode off"}
    </button>
  );
}

export function CommandBand() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { mode, setMode } = useWorkMode();
  const { state, enabled, unavailable } = useOttoStatus();
  const [text, setText] = useState("");
  const [autonomy, setAutonomy] = useState<Autonomy>("draft");
  const now = useClock();

  const { data: usage, isError: usageError } = useQuery({
    queryKey: ["usage"],
    queryFn: api.usage,
    enabled,
    refetchInterval: 60_000,
  });
  const { data: settings, isError: settingsError } = useQuery({
    queryKey: ["settings"],
    queryFn: api.settings,
    enabled,
  });
  const { data: connectors, isError: connectorsError } = useQuery({
    queryKey: ["connectors"],
    queryFn: api.connectors,
    enabled,
    refetchInterval: 60_000,
  });
  const toggleSafe = useMutation({
    mutationFn: () => api.patchSettings({ safe_mode: !settings?.safe_mode }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["briefing"] });
    },
  });

  // Kill switch is a real, known halt; an unreachable control plane is a separate "unknown"
  // state. Neither is allowed to render as calm "Steady" (F6).
  const killed = settings?.kill_switch === true;
  const statusBroken = unavailable || settingsError;
  const pulseState = killed ? "error" : state;
  const statusColor = killed
    ? OTTO_STATUS.error.color
    : statusBroken
      ? "var(--muted)"
      : OTTO_STATUS[state].color;
  const statusLabel = killed
    ? "Halted — kill switch engaged"
    : statusBroken
      ? "Status unavailable"
      : OTTO_STATUS[state].label;
  const statusSub = killed
    ? "Nothing executes until you release it in Settings."
    : statusBroken
      ? "Couldn't reach the control plane — retrying."
      : OTTO_STATUS[state].sub;

  const okCount = connectors?.filter((c) => c.health === "ok").length ?? 0;
  const mockCount = connectors?.filter((c) => c.health === "mock").length ?? 0;

  const submit = (preview: boolean) => {
    const q = new URLSearchParams();
    if (text.trim()) q.set("prefill", text.trim());
    q.set("mode", autonomy);
    q.set(preview ? "preview" : "autosubmit", "1");
    setText("");
    router.push(`/command?${q.toString()}`);
  };

  return (
    <div className="sticky top-0 z-30 border-b border-line bg-gradient-to-b from-nav to-background px-5 py-4 sm:px-7">
      <div className="flex flex-wrap items-center gap-x-7 gap-y-3">
        <div className="flex min-w-0 items-center gap-5">
          <OttoPulse state={pulseState} size={mode === "deep" ? 44 : 72} showLabel={false} />
          <div className="min-w-0">
            <div className="section-label">Otto — Chief of Staff</div>
            <div
              className="mt-1 truncate text-[19px] font-semibold leading-tight tracking-[-0.01em]"
              style={{ color: statusColor }}
              aria-live="polite"
            >
              {statusLabel}
            </div>
            {mode !== "deep" ? (
              <div className="mt-0.5 truncate text-[12.5px] text-muted-2">{statusSub}</div>
            ) : null}
          </div>
        </div>

        {/* Mobile-reachable Safe Mode: the desktop nav pill is hidden below lg, so the emergency
            gate lives here too so it's one tap on a phone (F3). Distinct testid — the nav pill
            keeps `safe-mode-pill`. */}
        {enabled ? (
          <SafeModePill
            settings={settings}
            isPending={toggleSafe.isPending}
            onToggle={() => toggleSafe.mutate()}
            testid="safe-mode-pill-mobile"
            className="shrink-0 lg:hidden"
          />
        ) : null}

        {mode !== "deep" ? (
          <>
            {/* home-composer: preserved compatibility id for the relocated Briefing composer (F12);
                the input itself keeps band-composer. On phones it STACKS — a full-width input above a
                wrapping row that shows every control (mode selector + Preview + Execute), so mobile
                gets the same actions as the desktop band instead of collapsing to just Execute.
                At md+ it is the original single inline row (unchanged). */}
            <div
              data-testid="home-composer"
              className="flex min-w-[240px] flex-1 flex-col items-stretch gap-2.5 rounded-[14px] border border-line-control bg-raised p-2.5 md:flex-row md:flex-wrap md:items-center md:gap-3 md:py-2 md:pl-4 md:pr-2"
            >
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && text.trim()) submit(false);
                }}
                placeholder="Direct the system, define an objective, or ask a question…"
                aria-label="Command Otto"
                data-testid="band-composer"
                className="min-h-[40px] w-full bg-transparent px-2 text-[15px] text-ink outline-none placeholder:text-muted/70 md:min-h-0 md:w-auto md:flex-1 md:px-0"
              />
              <div className="flex flex-wrap items-center justify-between gap-2.5 md:flex-none md:justify-start">
                <SegmentedControl
                  options={AUTONOMY.map((a) => ({ value: a.value, label: a.label }))}
                  value={autonomy}
                  onChange={(v) => setAutonomy(v)}
                  label="Execution mode"
                />
                <div className="flex items-center gap-2.5">
                  <button
                    onClick={() => submit(true)}
                    className="rounded-[9px] border border-line-button px-4 py-2 text-[13.5px] font-medium text-ink-soft hover:border-faint hover:text-ink"
                  >
                    Preview plan
                  </button>
                  <button
                    onClick={() => submit(false)}
                    data-testid="band-execute"
                    className="rounded-[9px] bg-accent px-5 py-2 text-[13.5px] font-semibold text-on-accent hover:bg-accent-hover"
                  >
                    Execute
                  </button>
                </div>
              </div>
            </div>

            <div className="ml-auto hidden flex-col items-end gap-2 xl:flex">
              <div className="font-mono text-[11.5px] font-medium tracking-[0.08em] text-muted-2">
                {now
                  ? now
                      .toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })
                      .toUpperCase() + " · " + now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                  : "—"}
              </div>
              <div className="flex flex-wrap justify-end gap-2">
                <span className="rounded-full border border-(--accent-border) px-3 py-1 font-mono text-[11px] font-medium text-accent-hover">
                  {usage
                    ? `BUDGET $${usage.today.cost_usd.toFixed(2)} / $${usage.budgets.daily_usd.toFixed(2)}`
                    : usageError
                      ? "BUDGET — UNAVAILABLE"
                      : "BUDGET …"}
                </span>
                <span className="rounded-full border border-line-control px-3 py-1 font-mono text-[11px] font-medium text-muted-2">
                  {connectors
                    ? `SYSTEMS ${okCount} OK${mockCount ? ` · ${mockCount} MOCK` : ""}`
                    : connectorsError
                      ? "SYSTEMS — UNAVAILABLE"
                      : "SYSTEMS …"}
                </span>
                <SegmentedControl
                  options={WORK_MODES}
                  value={mode}
                  onChange={setMode}
                  size="sm"
                  mono
                  label="Work mode"
                  className="rounded-full"
                />
              </div>
            </div>
          </>
        ) : (
          <div className="flex flex-1 flex-wrap items-center justify-end gap-5">
            <span className="otto-voice text-[16px] text-muted">
              Deep work — interruptions hidden. Active work keeps running; approvals wait quietly in the queue.
            </span>
            <button
              onClick={() => setMode("command")}
              className="rounded-full border border-line-button px-4 py-1.5 text-[13px] font-medium text-ink-soft hover:border-faint hover:text-ink"
            >
              Exit — Esc
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// Trust strip (spec §06): the system continuously discloses — closes every screen. When its
// read fails it says so; it never invents a provider or a Safe Mode value (F6).
export function TrustStrip() {
  const { data: settings, isError, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: api.settings,
  });
  const provider = settings?.provider;
  const providerOk = provider ? settings?.providers?.[provider]?.available : undefined;
  return (
    <div className="flex flex-wrap items-center gap-x-7 gap-y-1 border-t border-line px-5 py-2.5 text-[11.5px] text-faint sm:px-7">
      <span className="font-mono tracking-[0.08em]">OTTOOS · LOCAL-FIRST</span>
      <span>
        {settings
          ? settings.kill_switch
            ? "Kill switch engaged — worker halted"
            : settings.safe_mode
              ? "Safe Mode on — external writes blocked"
              : "Safe Mode off"
          : isError
            ? "Safe Mode — status unavailable"
            : "Safe Mode — checking…"}
      </span>
      <span>
        {provider
          ? `Provider — ${provider}${providerOk === undefined ? "" : providerOk ? ", healthy" : ", needs setup"}`
          : isLoading
            ? "Provider — checking…"
            : "Provider — unavailable"}
      </span>
      <span className="ml-auto text-muted-2">
        Every action audited · rollback available · <span className="text-accent-hover">you hold the pen</span>
      </span>
    </div>
  );
}
