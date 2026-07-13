"use client";

// Settings: appearance, safety (Safe Mode + kill switch), budgets, storage/export,
// memory review, domain permissions, policy editor (the ONLY place for allow rules).
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { CardSkeleton, ErrorState } from "@/components/ui/states";
import { applyTheme } from "@/components/cockpit/theme-toggle";
import { Download, Trash2 } from "lucide-react";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { data: settings, isLoading, error, refetch } = useQuery({
    queryKey: ["settings"], queryFn: api.settings,
  });
  const { data: usage } = useQuery({ queryKey: ["usage"], queryFn: api.usage });
  const { data: domains } = useQuery({ queryKey: ["domains"], queryFn: api.domains });
  const { data: proposedMemories } = useQuery({
    queryKey: ["memories", "proposed"], queryFn: () => api.memories("proposed"),
  });
  const { data: policies } = useQuery({ queryKey: ["policies"], queryFn: api.policies });

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

  if (isLoading) return <div className="mx-auto max-w-3xl"><CardSkeleton lines={8} /></div>;
  if (error || !settings) {
    return <div className="mx-auto max-w-3xl">
      <ErrorState detail={(error as Error)?.message} onRetry={() => refetch()} /></div>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-xl font-bold tracking-tight">Settings</h1>

      <Card>
        <CardHeader title="Safety" subtitle="Deterministic controls — no prompt can change these." />
        <CardBody className="space-y-3">
          <SettingRow
            title="Safe Mode"
            description="Blocks every external write, regardless of skill or approval."
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
                      description="Used when a command doesn't specify one.">
            <Select value={settings.default_mode}
                    onChange={(e) => patch.mutate({ default_mode: e.target.value })}
                    aria-label="Default execution mode">
              <option value="read_only">Read-only</option>
              <option value="draft">Draft</option>
              <option value="act">Act</option>
            </Select>
          </SettingRow>
          <SettingRow title="Reasoning provider"
                      description={settings.providers[settings.provider]?.detail
                        ?? "Pick who does the thinking. Keys & models live in Integrations."}>
            <Select value={settings.provider}
                    onChange={(e) => patch.mutate({ provider: e.target.value, model: "" })}
                    aria-label="Provider">
              <option value="mock">Demo runtime</option>
              <option value="claude">Claude</option>
              <option value="openai">OpenAI</option>
              <option value="ollama">Ollama (local)</option>
            </Select>
          </SettingRow>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Appearance" />
        <CardBody>
          <SettingRow title="Theme" description="Parchment light or midnight dark.">
            <Select defaultValue={typeof window !== "undefined"
                      ? localStorage.getItem("cockpit-theme") ?? "system" : "system"}
                    onChange={(e) => applyTheme(e.target.value)} aria-label="Theme">
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </Select>
          </SettingRow>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Budgets"
                    subtitle={usage ? `Today: $${usage.today.cost_usd.toFixed(2)} across ${usage.today.runs} runs · week: $${usage.week.cost_usd.toFixed(2)}` : undefined} />
        <CardBody className="grid gap-3 sm:grid-cols-2">
          <Field label="Daily budget (USD)">
            <Input type="number" min={0} step="0.5" defaultValue={settings.daily_budget_usd}
                   onBlur={(e) => patch.mutate({ daily_budget_usd: Number(e.target.value) })} />
          </Field>
          <Field label="Per-run budget (USD)">
            <Input type="number" min={0} step="0.1" defaultValue={settings.run_budget_usd}
                   onBlur={(e) => patch.mutate({ run_budget_usd: Number(e.target.value) })} />
          </Field>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Storage & export" subtitle={`Data directory: ${settings.data_dir}`} />
        <CardBody className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Obsidian vault path">
              <Input defaultValue={settings.vault_path ?? ""}
                     onBlur={(e) => patch.mutate({ vault_path: e.target.value || null })} />
            </Field>
            <Field label="Ideas folder path">
              <Input defaultValue={settings.bizideas_path ?? ""}
                     onBlur={(e) => patch.mutate({ bizideas_path: e.target.value || null })} />
            </Field>
          </div>
          <div className="flex flex-wrap gap-2">
            <a href={api.memoriesExportUrl()} download>
              <Button size="sm"><Download className="size-3.5" /> Export memories (JSON)</Button>
            </a>
            <Button size="sm" variant="ghost"
                    onClick={() => api.knowledgeReindex().then(() =>
                      queryClient.invalidateQueries({ queryKey: ["knowledge"] }))}>
              Rebuild knowledge index
            </Button>
          </div>
          <p className="text-[12px] text-muted">
            Backup = copy the data directory. Artifacts are plain Markdown/JSON on disk.
          </p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Memory review"
                    subtitle="Otto proposes; you decide. Nothing is remembered silently."
                    action={proposedMemories?.length
                      ? <Badge tone="warn">{proposedMemories.length} proposed</Badge> : undefined} />
        <CardBody>
          {(proposedMemories ?? []).length === 0 ? (
            <p className="text-[13px] text-muted">No proposals waiting. Run Commitment Sweep to scan your notes.</p>
          ) : (
            <ul className="space-y-2" data-testid="memory-review">
              {(proposedMemories ?? []).map((memory) => (
                <li key={memory.id} className="rounded-[10px] border border-line bg-raised p-3">
                  <p className="text-[13.5px]">{memory.content}</p>
                  <p className="mt-0.5 text-[12px] text-muted">
                    {memory.kind} · confidence {(memory.confidence * 100).toFixed(0)}% · {memory.rationale}
                  </p>
                  <div className="mt-2 flex gap-2">
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
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Domains"
                    subtitle="High-sensitivity domains (health, money) stay read-only and off by default." />
        <CardBody>
          <ul className="grid gap-2 sm:grid-cols-2">
            {(domains ?? []).map((domain) => (
              <li key={domain.key}
                  className="flex items-center justify-between rounded-[10px] border border-line bg-raised px-3.5 py-2.5">
                <div>
                  <p className="text-[13.5px] font-medium">{domain.name}</p>
                  <p className="text-[11.5px] text-muted">
                    {domain.sensitivity === "high" ? "high sensitivity · read-only" : domain.read_only ? "read-only" : "read/write"}
                  </p>
                </div>
                <Switch checked={domain.enabled} label={`${domain.name} domain enabled`}
                        onChange={(v) => patchDomain.mutate({ key: domain.key, body: { enabled: v } })} />
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Policies"
                    subtitle="The only place 'always allow' rules can be created — deliberately away from approval cards." />
        <CardBody className="space-y-3">
          {(policies ?? []).length === 0 ? (
            <p className="text-[13px] text-muted">No custom rules. Defaults apply: reads auto, local writes draft-gated, external writes approval-gated, R4 disabled.</p>
          ) : (
            <ul className="space-y-1.5">
              {(policies ?? []).map((policy) => (
                <li key={policy.id} className="flex items-center justify-between gap-2 rounded-[10px] border border-line bg-raised px-3.5 py-2 text-[13px]">
                  <span>
                    <Badge tone={policy.kind === "deny" ? "danger" : policy.kind === "confirm" ? "warn" : "accent"}>
                      {policy.kind}
                    </Badge>{" "}
                    <span className="font-mono text-[12px]">
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
        </CardBody>
      </Card>
    </div>
  );
}

function SettingRow({ title, description, children, danger }: {
  title: string; description: string; children: React.ReactNode; danger?: boolean;
}) {
  return (
    <div className={`flex items-center justify-between gap-4 rounded-[10px] border px-3.5 py-3 ${
      danger ? "border-danger/40 bg-danger-soft/40" : "border-line bg-raised"}`}>
      <div>
        <p className="text-[13.5px] font-medium">{title}</p>
        <p className="text-[12.5px] text-muted">{description}</p>
      </div>
      {children}
    </div>
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
    <div className="flex flex-wrap items-end gap-2 border-t border-line pt-3">
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
