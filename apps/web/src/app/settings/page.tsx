"use client";

// Settings: appearance, safety (Safe Mode + kill switch), budgets, storage/export,
// memory review, domain permissions, policy editor (the ONLY place for allow rules).
// OttoOS restyle — same endpoints, mutations, and testids; presentation only.
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfidenceTag } from "@/components/ui/confidence";
import { Field, Input, Select } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented";
import { CardSkeleton, ErrorState, SectionLabel, Skeleton } from "@/components/ui/states";
import { Switch } from "@/components/ui/switch";
import { applyTheme } from "@/components/cockpit/theme-toggle";
import { Download, Trash2 } from "lucide-react";

type ExecMode = "read_only" | "draft" | "act";
const EXEC_MODES: { value: ExecMode; label: string }[] = [
  { value: "read_only", label: "Advise" },
  { value: "draft", label: "Draft" },
  { value: "act", label: "Act" },
];

type ThemeChoice = "dark" | "light" | "system";
const THEME_OPTIONS: { value: ThemeChoice; label: string }[] = [
  { value: "dark", label: "MIDNIGHT" },
  { value: "light", label: "PARCHMENT" },
  { value: "system", label: "SYSTEM" },
];

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { data: settings, isLoading, error, refetch } = useQuery({
    queryKey: ["settings"], queryFn: api.settings,
  });
  const { data: usage } = useQuery({ queryKey: ["usage"], queryFn: api.usage });
  const { data: domains, isLoading: domainsLoading } = useQuery({
    queryKey: ["domains"], queryFn: api.domains,
  });
  const { data: proposedMemories, isLoading: memoriesLoading } = useQuery({
    queryKey: ["memories", "proposed"], queryFn: () => api.memories("proposed"),
  });
  const { data: policies, isLoading: policiesLoading } = useQuery({
    queryKey: ["policies"], queryFn: api.policies,
  });

  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patchSettings(body),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
      queryClient.invalidateQueries({ queryKey: ["briefing"] });
    },
  });
  const patchDomain = useMutation({
    mutationFn: ({ key, body }: { key: string; body: { enabled?: boolean } }) =>
      api.patchDomain(key, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["domains"] }),
  });
  const reviewMemory = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" }) =>
      api.reviewMemory(id, { action }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["memories"] }),
  });
  const deletePolicy = useMutation({
    mutationFn: (id: string) => api.deletePolicy(id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["policies"] }),
  });
  const reindex = useMutation({
    mutationFn: () => api.knowledgeReindex(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["knowledge"] }),
  });

  if (isLoading) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-5">
        <CardSkeleton lines={8} />
        <CardSkeleton lines={4} />
      </div>
    );
  }
  if (error || !settings) {
    return (
      <div className="mx-auto w-full max-w-4xl">
        <ErrorState detail={(error as Error)?.message} onRetry={() => refetch()} />
      </div>
    );
  }

  return (
    <div className="fadeup mx-auto w-full max-w-4xl space-y-5">
      <h1 className="text-[26px] font-semibold tracking-[-0.3px]">Settings</h1>

      <SettingsCard
        label="Safety"
        description="Deterministic controls — no prompt can change these."
      >
        <div className="mt-1">
          <SettingRow
            title="Safe Mode"
            description="Blocks every external write, regardless of agent or approval."
          >
            <Switch checked={settings.safe_mode} label="Safe Mode"
                    onChange={(v) => patch.mutate({ safe_mode: v })} />
          </SettingRow>
          <SettingRow
            title="Kill switch"
            description="Halts the worker completely. Nothing executes until released."
            danger
          >
            <Switch checked={settings.kill_switch} tone="danger" label="Kill switch"
                    onChange={(v) => patch.mutate({ kill_switch: v })} />
          </SettingRow>
          <SettingRow title="Default execution mode"
                      description={"Used when a command doesn't specify one."}>
            <SegmentedControl<ExecMode>
              options={EXEC_MODES}
              value={settings.default_mode}
              onChange={(v) => patch.mutate({ default_mode: v })}
              label="Default execution mode"
              size="sm"
            />
          </SettingRow>
          <SettingRow
            title="Reasoning provider"
            description={
              <>
                {settings.providers[settings.provider]?.detail ?? "Pick who does the thinking."}{" "}
                Keys &amp; models live in Systems.
              </>
            }
          >
            <Select value={settings.provider}
                    onChange={(e) => patch.mutate({ provider: e.target.value, model: "" })}
                    aria-label="Provider">
              <option value="mock">Demo runtime</option>
              <option value="claude">Claude</option>
              <option value="openai">OpenAI</option>
              <option value="ollama">Ollama (local)</option>
            </Select>
          </SettingRow>
        </div>
      </SettingsCard>

      <SettingsCard label="Appearance">
        <div className="mt-1">
          <SettingRow title="Theme"
                      description="Midnight graphite (this cockpit) or parchment light — or follow the system.">
            <ThemeControl />
          </SettingRow>
        </div>
      </SettingsCard>

      <SettingsCard
        label="Budgets"
        description={
          <>
            {usage
              ? `Today: $${usage.today.cost_usd.toFixed(2)} across ${usage.today.runs} runs · week: $${usage.week.cost_usd.toFixed(2)}. `
              : null}
            Hard stops, enforced in code.
          </>
        }
      >
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Daily budget (USD)">
            <Input type="number" min={0} step="0.5" defaultValue={settings.daily_budget_usd}
                   className="font-mono text-[13px]"
                   onBlur={(e) => patch.mutate({ daily_budget_usd: Number(e.target.value) })} />
          </Field>
          <Field label="Per-run budget (USD)">
            <Input type="number" min={0} step="0.1" defaultValue={settings.run_budget_usd}
                   className="font-mono text-[13px]"
                   onBlur={(e) => patch.mutate({ run_budget_usd: Number(e.target.value) })} />
          </Field>
        </div>
      </SettingsCard>

      <SettingsCard
        label="Storage & export"
        description={
          <span className="font-mono text-[11.5px] text-muted-2">
            <span className="text-faint">DATA</span> {settings.data_dir}
          </span>
        }
      >
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Obsidian vault path">
              <Input defaultValue={settings.vault_path ?? ""}
                     className="font-mono text-[12.5px]"
                     onBlur={(e) => patch.mutate({ vault_path: e.target.value || null })} />
            </Field>
            <Field label="Ideas folder path">
              <Input defaultValue={settings.bizideas_path ?? ""}
                     className="font-mono text-[12.5px]"
                     onBlur={(e) => patch.mutate({ bizideas_path: e.target.value || null })} />
            </Field>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href={api.memoriesExportUrl()} download>
              <Button size="sm"><Download className="size-3.5" /> Export memories (JSON)</Button>
            </a>
            <Button size="sm" variant="ghost" busy={reindex.isPending}
                    onClick={() => reindex.mutate()}>
              Rebuild knowledge index
            </Button>
          </div>
          <p className="text-[12.5px] text-faint">
            Backup = copy the data directory. Artifacts are plain Markdown/JSON on disk.
          </p>
        </div>
      </SettingsCard>

      <SettingsCard
        label="Memory review"
        description="Otto proposes; you decide. Nothing is remembered silently."
        action={proposedMemories?.length
          ? <Badge tone="warn">{proposedMemories.length} proposed</Badge> : undefined}
      >
        {memoriesLoading ? (
          <Skeleton className="mt-4 h-14 w-full" />
        ) : (proposedMemories ?? []).length === 0 ? (
          <div className="mt-3">
            <p className="otto-voice text-[15.5px] text-ink-soft">No proposals waiting.</p>
            <p className="mt-1 text-[12.5px] text-muted">Run Commitment Sweep to scan your notes.</p>
          </div>
        ) : (
          <ul className="mt-4 space-y-2.5" data-testid="memory-review">
            {(proposedMemories ?? []).map((memory) => (
              <li key={memory.id} className="rounded-[11px] border border-line-row bg-tile px-4 py-3.5">
                <p className="text-[13.5px] leading-relaxed">{memory.content}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12px] text-muted">
                  <Badge tone="muted">{memory.kind}</Badge>
                  <ConfidenceTag value={memory.confidence} />
                  <span>{memory.rationale}</span>
                </div>
                <div className="mt-2.5 flex gap-2">
                  <Button size="sm" variant="primary"
                          onClick={() => reviewMemory.mutate({ id: memory.id, action: "approve" })}>
                    Approve
                  </Button>
                  <Button size="sm" variant="ghost"
                          onClick={() => reviewMemory.mutate({ id: memory.id, action: "reject" })}>
                    Reject
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </SettingsCard>

      <SettingsCard
        label="Domains"
        description="High-sensitivity domains (health, money) stay read-only and off by default."
      >
        {domainsLoading ? (
          <Skeleton className="mt-4 h-14 w-full" />
        ) : (domains ?? []).length === 0 ? (
          <p className="mt-3 text-[13px] text-muted">No domains registered.</p>
        ) : (
          <ul className="mt-4 grid gap-2.5 sm:grid-cols-2">
            {(domains ?? []).map((domain) => (
              <li key={domain.key}
                  className="flex items-center justify-between gap-4 rounded-[11px] border border-line-row bg-tile px-4 py-3">
                <div className="min-w-0">
                  <p className="text-[13.5px] font-medium">{domain.name}</p>
                  <p className="mt-0.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-faint">
                    {domain.sensitivity === "high"
                      ? "high sensitivity · read-only"
                      : domain.read_only ? "read-only" : "read/write"}
                  </p>
                </div>
                <Switch checked={domain.enabled} label={`${domain.name} domain enabled`}
                        onChange={(v) => patchDomain.mutate({ key: domain.key, body: { enabled: v } })} />
              </li>
            ))}
          </ul>
        )}
      </SettingsCard>

      <SettingsCard
        label={"Policies · “always allow” registry"}
        description={"The only place 'always allow' rules can be created — deliberately away from approval cards. R4 stays disabled unless double-confirmed with a typed phrase."}
      >
        <div className="mt-4 space-y-4">
          {policiesLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : (policies ?? []).length === 0 ? (
            <p className="text-[13px] text-muted">
              No custom rules. Defaults apply: reads auto, local writes draft-gated, external
              writes approval-gated, R4 disabled.
            </p>
          ) : (
            <ul className="space-y-2">
              {(policies ?? []).map((policy) => (
                <li key={policy.id}
                    className="flex items-center justify-between gap-2 rounded-[11px] border border-line-row bg-tile px-4 py-2.5 text-[13px]">
                  <span className="min-w-0">
                    <Badge tone={policy.kind === "deny" ? "danger" : policy.kind === "confirm" ? "warn" : "accent"}>
                      {policy.kind}
                    </Badge>{" "}
                    <span className="font-mono text-[12px] text-ink-soft">
                      {policy.tool_id ?? policy.connector_slug ?? policy.skill_slug}
                    </span>
                    {policy.note ? <span className="text-muted"> — {policy.note}</span> : null}
                  </span>
                  <Button size="sm" variant="ghost" aria-label={`Delete rule ${policy.name}`}
                          onClick={() => deletePolicy.mutate(policy.id)}>
                    <Trash2 className="size-3.5" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <PolicyCreator />
        </div>
      </SettingsCard>
    </div>
  );
}

// Card shell: mono section label + honest description, spec §01 geometry.
function SettingsCard({ label, description, action, children }: {
  label: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card className="px-6 py-5 sm:px-7">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SectionLabel>{label}</SectionLabel>
        {action}
      </div>
      {description ? (
        <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-muted">{description}</p>
      ) : null}
      {children}
    </Card>
  );
}

// Hairline-separated setting row; the kill switch gets a calm danger-tinted tile.
function SettingRow({ title, description, children, danger }: {
  title: string; description: React.ReactNode; children: React.ReactNode; danger?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-x-6 gap-y-3",
        danger
          ? "my-2 rounded-[11px] border border-danger/25 bg-danger-soft/40 px-4 py-3.5"
          : "border-b border-line-row py-4 last:border-b-0 last:pb-1",
      )}
    >
      <div className="min-w-0 flex-1 basis-60">
        <p className={cn("text-[14.5px] font-medium", danger && "text-danger")}>{title}</p>
        <p className="mt-0.5 text-[12.5px] text-muted">{description}</p>
      </div>
      {children}
    </div>
  );
}

// Theme preference is local (applied to <html data-theme>) — values dark/light/system.
function ThemeControl() {
  // Initialize to a server-stable value; read the stored preference only AFTER mount so the
  // first client render matches the SSR HTML (no hydration mismatch — same reason ThemeToggle
  // gates on mount rather than reading localStorage during the initial render).
  const [theme, setTheme] = useState<ThemeChoice>("system");
  useEffect(() => {
    const saved = localStorage.getItem("cockpit-theme");
    if (saved === "dark" || saved === "light" || saved === "system") setTheme(saved);
  }, []);
  return (
    <SegmentedControl<ThemeChoice>
      options={THEME_OPTIONS}
      value={theme}
      onChange={(v) => {
        setTheme(v);
        applyTheme(v);
      }}
      label="Theme"
      size="sm"
      mono
    />
  );
}

function PolicyCreator() {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<"allow" | "deny" | "confirm">("deny");
  const [toolId, setToolId] = useState("");
  const create = useMutation({
    mutationFn: () =>
      api.createPolicy({ name: `${kind} ${toolId}`, kind, tool_id: toolId }),
    onSuccess: () => {
      setToolId("");
      queryClient.invalidateQueries({ queryKey: ["policies"] });
    },
  });
  return (
    <div className="flex flex-wrap items-end gap-2.5 border-t border-line-row pt-4">
      <Field label="Rule">
        <Select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          <option value="deny">deny — block a tool entirely</option>
          <option value="allow">allow — allowlist for autonomy level 5</option>
          <option value="confirm">confirm — enable R4 double-confirm</option>
        </Select>
      </Field>
      <Field label="Tool id">
        <Input value={toolId} onChange={(e) => setToolId(e.target.value)}
               placeholder="e.g. n8n.crm_sync" className="w-56 font-mono text-[12.5px]" />
      </Field>
      <Button size="md" busy={create.isPending} disabled={!toolId.trim()}
              onClick={() => create.mutate()}>
        Add rule
      </Button>
      {create.isError ? (
        <p role="alert" className="w-full text-[12.5px] text-danger">{(create.error as Error).message}</p>
      ) : null}
    </div>
  );
}
