"use client";

// The command band (OttoOS spec §04/§05): Otto hero + status, the persistent composer with
// autonomy segments, and vitals (clock, budget, systems, work-mode). In Deep Work it slims
// to Otto-mini + "Otto holds interruptions". The trust strip closes every screen.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { ACTIVE_RUN_STATUSES, cn } from "@/lib/utils";
import { deriveOttoState, OTTO_STATUS, OttoPulse } from "@/components/cockpit/otto-pulse";
import { useWorkMode, type WorkMode } from "@/components/cockpit/work-mode";
import { SegmentedControl } from "@/components/ui/segmented";

// Autonomy segments map 1:1 to run modes (spec §03); In-policy = act within the allowlist —
// the policy gateway still decides, exactly as before.
const AUTONOMY = [
  { value: "read_only", label: "Advise" },
  { value: "draft", label: "Draft" },
  { value: "act", label: "Execute + approval" },
  { value: "allowlist", label: "In-policy" },
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
  const { data: activeRuns } = useQuery({
    queryKey: ["runs", "active"],
    queryFn: () => api.runs({ status: ACTIVE_RUN_STATUSES.join(",") }),
    enabled,
    refetchInterval: 15_000,
  });
  const { data: pending } = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => api.approvals("pending"),
    enabled,
    refetchInterval: 30_000,
  });
  const state = deriveOttoState(activeRuns ?? [], pending?.length ?? 0);
  return { state, activeRuns: activeRuns ?? [], pending: pending ?? [], enabled };
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

export function CommandBand() {
  const router = useRouter();
  const { mode, setMode } = useWorkMode();
  const { state, enabled } = useOttoStatus();
  const [text, setText] = useState("");
  const [autonomy, setAutonomy] = useState<Autonomy>("draft");
  const now = useClock();

  const { data: usage } = useQuery({
    queryKey: ["usage"],
    queryFn: api.usage,
    enabled,
    refetchInterval: 60_000,
  });
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled });
  const { data: connectors } = useQuery({
    queryKey: ["connectors"],
    queryFn: api.connectors,
    enabled,
    refetchInterval: 60_000,
  });

  const status = OTTO_STATUS[settings?.kill_switch ? "error" : state];
  const statusLabel = settings?.kill_switch ? "Halted — kill switch engaged" : status.label;
  const statusSub = settings?.kill_switch
    ? "Nothing executes until you release it in Settings."
    : status.sub;

  const ok = (connectors ?? []).filter((c) => c.health === "ok").length;
  const mock = (connectors ?? []).filter((c) => c.health === "mock").length;

  const submit = (preview: boolean) => {
    const q = new URLSearchParams();
    if (text.trim()) q.set("prefill", text.trim());
    q.set("mode", autonomy === "allowlist" ? "act" : autonomy);
    q.set(preview ? "preview" : "autosubmit", "1");
    setText("");
    router.push(`/command?${q.toString()}`);
  };

  return (
    <div className="sticky top-0 z-30 border-b border-line bg-gradient-to-b from-nav to-background px-5 py-4 sm:px-7">
      <div className="flex flex-wrap items-center gap-x-7 gap-y-3">
        <div className="flex min-w-0 items-center gap-5">
          <OttoPulse state={settings?.kill_switch ? "error" : state} size={mode === "deep" ? 44 : 72} showLabel={false} />
          <div className="min-w-0">
            <div className="section-label">Otto — Chief of Staff</div>
            <div
              className="mt-1 truncate text-[19px] font-semibold leading-tight tracking-[-0.01em]"
              style={{ color: status.color }}
              aria-live="polite"
            >
              {statusLabel}
            </div>
            {mode !== "deep" ? (
              <div className="mt-0.5 truncate text-[12.5px] text-muted-2">{statusSub}</div>
            ) : null}
          </div>
        </div>

        {mode !== "deep" ? (
          <>
            <div className="flex min-w-[240px] flex-1 flex-wrap items-center gap-3 rounded-[14px] border border-line-control bg-raised py-2 pl-4 pr-2">
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && text.trim()) submit(false);
                }}
                placeholder="Direct the system, define an objective, or ask a question…"
                aria-label="Command Otto"
                data-testid="band-composer"
                className="min-w-[160px] flex-1 bg-transparent text-[15px] text-ink outline-none placeholder:text-muted/70"
              />
              <div className="flex flex-none flex-wrap items-center gap-2.5">
                <SegmentedControl
                  options={AUTONOMY.map((a) => ({ value: a.value, label: a.label }))}
                  value={autonomy}
                  onChange={(v) => setAutonomy(v)}
                  label="Autonomy"
                  className="hidden md:inline-flex"
                />
                <button
                  onClick={() => submit(true)}
                  className="hidden rounded-[9px] border border-line-button px-4 py-2 text-[13.5px] font-medium text-ink-soft hover:border-faint hover:text-ink sm:block"
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
                  BUDGET ${(usage?.today.cost_usd ?? 0).toFixed(2)} / ${(usage?.budgets.daily_usd ?? 5).toFixed(2)}
                </span>
                <span className="rounded-full border border-line-control px-3 py-1 font-mono text-[11px] font-medium text-muted-2">
                  SYSTEMS {ok} OK{mock ? ` · ${mock} MOCK` : ""}
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
              Deep work — Otto holds interruptions. Approvals wait; nothing executes.
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

// Trust strip (spec §06): the system continuously discloses — closes every screen.
export function TrustStrip() {
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const provider = settings?.provider ?? "mock";
  const providerOk = settings?.providers?.[provider]?.available;
  return (
    <div className="flex flex-wrap items-center gap-x-7 gap-y-1 border-t border-line px-5 py-2.5 text-[11.5px] text-faint sm:px-7">
      <span className="font-mono tracking-[0.08em]">OTTOOS · LOCAL-FIRST</span>
      <span>
        {settings?.kill_switch
          ? "Kill switch engaged — worker halted"
          : settings?.safe_mode
            ? "Safe Mode on — external writes blocked"
            : "Safe Mode off"}
      </span>
      <span>
        Provider — {provider}
        {providerOk === undefined ? "" : providerOk ? ", healthy" : ", needs setup"}
      </span>
      <span className="ml-auto text-muted-2">
        Every action audited · rollback available · <span className="text-accent-hover">you hold the pen</span>
      </span>
    </div>
  );
}
