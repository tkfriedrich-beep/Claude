"use client";

// Systems (/integrations, was Integrations) — pick a reasoning provider + model, manage API
// keys (write-only, local file), and add/edit/remove connectors (MCP servers, n8n webhooks).
// The policy gateway still decides what may actually run; mocked services are labeled until
// genuinely connected. Same endpoints and controls — presentation only (OttoOS).
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Connector, ProviderInfo, SecretSlot } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  CardSkeleton, EmptyState, ErrorState, SectionLabel, Skeleton,
} from "@/components/ui/states";
import { KeyRound, Plug, Plus, RefreshCw, Trash2 } from "lucide-react";

// Health chips (Systems spec): OK gold-outline · MOCK muted · DEGRADED amber · DOWN danger.
const HEALTH_TONE: Record<string, "accent" | "warn" | "danger" | "muted"> = {
  ok: "accent", mock: "muted", degraded: "warn", unavailable: "danger", unknown: "muted",
};
// Connectors whose registered resources (webhooks / servers) can be listed & removed.
const RESOURCE_KEY: Record<string, "webhooks" | "servers"> = { n8n: "webhooks", mcp: "servers" };

// Connector identity is a square mono tile — initials derived from the real name.
function connectorMono(name: string): string {
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length >= 2) return `${words[0][0]}${words[1][0]}`.toUpperCase();
  const caps = name.replace(/[^A-Z0-9]/g, "");
  return caps.length >= 2 ? caps.slice(0, 2) : name.slice(0, 2).toUpperCase();
}

const monoLink =
  "font-mono text-[11px] font-medium tracking-[0.06em] transition-colors " +
  "disabled:pointer-events-none disabled:opacity-50";

export default function IntegrationsPage() {
  const [addOpen, setAddOpen] = useState(false);
  const { data: connectors, isLoading, error, refetch } = useQuery({
    queryKey: ["connectors"], queryFn: api.connectors,
  });
  const list = connectors ?? [];

  return (
    <div className="fadeup mx-auto w-full max-w-6xl space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[26px] font-semibold tracking-[-0.3px]">Systems</h1>
          <p className="mt-1 max-w-2xl text-[14px] text-muted">
            Choose who does the thinking, add the keys that unlock services, and wire up the
            tools Otto can use. The policy gateway still gates every real action; mocked
            services are labeled until genuinely connected.
          </p>
        </div>
        <Button variant="primary" onClick={() => setAddOpen(true)}>
          <Plus className="size-4" /> Add MCP / n8n
        </Button>
      </header>

      <ProviderCard />
      <SecretsCard />

      <section className="space-y-3.5">
        <div className="flex flex-wrap items-baseline gap-3.5 px-1">
          <SectionLabel>Connectors</SectionLabel>
          {!isLoading && !error ? (
            <span className="text-[13px] text-muted">{list.length} wired</span>
          ) : null}
        </div>
        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2">
            {[1, 2, 3, 4].map((i) => <CardSkeleton key={i} lines={4} />)}
          </div>
        ) : error ? (
          <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
        ) : list.length === 0 ? (
          <EmptyState icon={<Plug />} title="Nothing is wired in yet."
                      hint="Register an MCP server or n8n webhook — every tool it exposes still needs your approval."
                      action={<Button onClick={() => setAddOpen(true)}>Add MCP / n8n</Button>} />
        ) : (
          <div className="grid gap-4 md:grid-cols-2" data-testid="connector-grid">
            {list.map((connector) => (
              <ConnectorCard key={connector.slug} connector={connector} />
            ))}
          </div>
        )}
      </section>
      <AddResourceDialog open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}

// ------------------------------------------------------------------ providers

// Mono status tags (Systems spec): SELECTED gold · READY · NEEDS SETUP. Gold marks
// selection only — availability comes straight from the providers endpoint.
function providerTag(p: ProviderInfo, selected: boolean): { label: string; cls: string } {
  if (selected) {
    return p.available
      ? { label: "selected · ready", cls: "text-accent-hover" }
      : { label: "selected · needs setup", cls: "text-danger" };
  }
  if (p.available) return { label: "ready", cls: "text-muted" };
  return { label: "needs setup", cls: p.id === "mock" ? "text-muted-2" : "text-danger" };
}

function ProviderCard() {
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["providers"], queryFn: api.providers,
  });
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["providers"] });
    queryClient.invalidateQueries({ queryKey: ["settings"] });
    queryClient.invalidateQueries({ queryKey: ["secrets"] });
  };
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patchSettings(body),
    onSettled: invalidate,
  });

  return (
    <Card className="px-6 py-5">
      <SectionLabel>Reasoning providers</SectionLabel>
      <p className="mt-1.5 text-[13px] text-muted">
        Who does the thinking. Everything runs locally except calls to the provider you pick.
      </p>
      {isLoading ? (
        <div className="mt-4 grid gap-3.5 sm:grid-cols-2" role="status" aria-label="Loading">
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </div>
      ) : error || !data ? (
        <div className="mt-4">
          <ErrorState detail={(error as Error)?.message} onRetry={() => refetch()} />
        </div>
      ) : (
        <>
          <div data-testid="provider-grid"
               className="mt-4 grid gap-3.5 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
            {data.providers.map((p) => {
              const selected = data.selected_provider === p.id;
              const tag = providerTag(p, selected);
              return (
                <button key={p.id} type="button"
                        onClick={() => patch.mutate({ provider: p.id, model: "" })}
                        aria-pressed={selected}
                        className={cn(
                          "rounded-[12px] border bg-tile px-5 py-4 text-left transition-colors",
                          selected
                            ? "border-(--accent-border)"
                            : "border-line-card hover:border-line-button",
                        )}>
                  <div className="flex items-baseline gap-2">
                    <span className="truncate text-[15px] font-medium">{p.name}</span>
                    <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted-2">
                      {p.kind}
                    </span>
                    <span className={cn(
                      "ml-auto shrink-0 font-mono text-[10.5px] uppercase tracking-[0.05em]",
                      tag.cls,
                    )}>
                      {tag.label}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[12.5px] text-muted">{p.detail}</p>
                </button>
              );
            })}
          </div>
          <ProviderConfig
            provider={data.providers.find((p) => p.id === data.selected_provider)}
            selectedModel={data.selected_model}
            onModel={(model) => patch.mutate({ model })}
            onSaved={invalidate}
          />
        </>
      )}
    </Card>
  );
}

function ProviderConfig({ provider, selectedModel, onModel, onSaved }: {
  provider?: ProviderInfo; selectedModel: string;
  onModel: (model: string) => void; onSaved: () => void;
}) {
  if (!provider) return null;
  const needsKey = provider.requires_secret && !provider.secret_configured;
  const modelOptions = provider.models.includes(selectedModel) || !selectedModel
    ? provider.models
    : [selectedModel, ...provider.models];

  return (
    <div className="mt-3.5 space-y-3.5 rounded-[12px] border border-line bg-tile px-5 py-4">
      {needsKey ? (
        <InlineSecret name={provider.requires_secret!} label={`${provider.name} API key`}
                      hint="Stored in a local, gitignored file (data/local/secrets.env) — never in the database or logs."
                      onSaved={onSaved} />
      ) : provider.requires_secret ? (
        <p className="text-[12.5px] text-muted">
          <KeyRound className="mr-1 inline size-3.5" />
          <span className="font-mono text-[12px] text-ink-soft">{provider.requires_secret}</span>
          {" "}is configured. Manage it under Secrets below.
        </p>
      ) : null}

      {provider.models.length > 0 || provider.id === "ollama" ? (
        <Field label="Model"
               hint={provider.id === "ollama"
                 ? "Installed local models (from `ollama pull`). Refresh after adding one."
                 : "Pick a model, or leave on Default."}>
          {modelOptions.length === 0 ? (
            <p className="text-[12.5px] text-muted">
              No models detected. {provider.available ? "Pull one with `ollama pull llama3`." : "Configure the provider first."}
            </p>
          ) : (
            <Select value={selectedModel} onChange={(e) => onModel(e.target.value)}
                    className="w-full" aria-label="Model">
              <option value="">Default{provider.default_model ? ` (${provider.default_model})` : ""}</option>
              {modelOptions.map((m) => <option key={m} value={m}>{m}</option>)}
            </Select>
          )}
        </Field>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ secrets

function SecretsCard() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["secrets"], queryFn: api.secrets,
  });
  const slots = data?.secrets ?? [];
  return (
    <Card className="px-6 py-5">
      <SectionLabel>Secrets</SectionLabel>
      <p className="mt-1.5 text-[13px] text-muted">
        API keys and webhook secrets. Values are write-only — saved to a local 0600 file, never
        shown back, never committed or logged.
      </p>
      <div className="mt-4 space-y-2.5">
        {isLoading ? (
          <div className="space-y-2.5" role="status" aria-label="Loading">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        ) : error ? (
          <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
        ) : slots.length === 0 ? (
          <p className="text-[13px] text-muted">
            No secret slots yet — provider and connector keys appear here.
          </p>
        ) : (
          slots.map((slot) => <SecretRow key={slot.name} slot={slot} />)
        )}
      </div>
    </Card>
  );
}

function SecretRow({ slot }: { slot: SecretSlot }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["secrets"] });
    queryClient.invalidateQueries({ queryKey: ["providers"] });
    queryClient.invalidateQueries({ queryKey: ["settings"] });
  };
  const remove = useMutation({
    mutationFn: () => api.deleteSecret(slot.name),
    onSettled: invalidate,
  });

  return (
    <div className="rounded-[11px] border border-line-row bg-tile px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 font-mono text-[12.5px] text-ink-soft">
            {slot.name}
            {slot.configured
              ? <Badge tone={slot.source === "env" ? "outline" : "accent"}>
                  {slot.source === "env" ? "from environment" : "set"}
                </Badge>
              : <Badge tone="muted">not set</Badge>}
          </p>
          <p className="mt-1 text-[12px] text-muted">{slot.description}</p>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <Button size="sm" variant="ghost" onClick={() => setEditing((v) => !v)}>
            {slot.configured ? "Update" : "Add"}
          </Button>
          {slot.deletable ? (
            <Button size="sm" variant="ghost" busy={remove.isPending}
                    aria-label={`Remove ${slot.name}`} onClick={() => remove.mutate()}>
              <Trash2 className="size-3.5" />
            </Button>
          ) : null}
        </div>
      </div>
      {slot.source === "env" ? (
        <p className="mt-1 text-[11.5px] text-faint">
          Set in your shell environment — it overrides any value saved here. Unset it there to change it.
        </p>
      ) : null}
      {editing ? (
        <div className="mt-2.5">
          <InlineSecret name={slot.name} label="" onSaved={() => { setEditing(false); invalidate(); }} />
        </div>
      ) : null}
    </div>
  );
}

// A write-only secret entry: type a value, save it, forget it. Never reads the value back.
function InlineSecret({ name, label, hint, onSaved }: {
  name: string; label: string; hint?: string; onSaved: () => void;
}) {
  const [value, setValue] = useState("");
  const save = useMutation({
    mutationFn: () => api.putSecret(name, value),
    onSuccess: () => { setValue(""); onSaved(); },
  });
  const field = (
    <div className="flex gap-2">
      <Input type="password" autoComplete="off" value={value} placeholder={`Paste ${name}…`}
             onChange={(e) => setValue(e.target.value)} className="font-mono" />
      <Button variant="primary" busy={save.isPending} disabled={!value.trim()}
              onClick={() => save.mutate()}>Save</Button>
    </div>
  );
  return (
    <div className="space-y-1">
      {label ? <Field label={label} hint={hint}>{field}</Field> : field}
      {save.isError ? <p className="text-[12px] text-danger">{(save.error as Error).message}</p> : null}
    </div>
  );
}

// ------------------------------------------------------------------ connectors

function ConnectorCard({ connector }: { connector: Connector }) {
  const queryClient = useQueryClient();
  const [toolsOpen, setToolsOpen] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const manifest = connector.manifest as Record<string, any>;
  const isMock = Boolean(manifest?.mock);
  const resourceKey = RESOURCE_KEY[connector.slug];
  const resources: any[] = resourceKey ? ((connector.config as any)?.[resourceKey] ?? []) : [];

  const check = useMutation({
    mutationFn: () => api.checkConnectorHealth(connector.slug),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["connectors"] }),
  });
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patchConnector(connector.slug, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["connectors"] }),
  });

  return (
    <Card className={cn("flex flex-col px-6 py-5", !connector.enabled && "opacity-60")}
          data-testid={`connector-${connector.slug}`}>
      <div className="flex items-start gap-3">
        <span aria-hidden
              className="flex size-[34px] shrink-0 items-center justify-center rounded-[9px] border border-line-button font-mono text-[11px] font-medium text-accent-hover">
          {connectorMono(connector.name)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15.5px] font-semibold tracking-[-0.01em]">{connector.name}</p>
          <p className="mt-0.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-muted-2">
            {connector.category}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <Badge tone={HEALTH_TONE[connector.health] ?? "muted"}>{connector.health}</Badge>
          {isMock ? <Badge tone="outline">mock — demo data</Badge> : null}
        </div>
      </div>

      <p className="mt-3 min-h-[38px] flex-1 text-[13px] leading-relaxed text-muted">
        {connector.health_detail || manifest?.description}
      </p>
      <p className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.05em] text-muted-2">
        last ok {connector.last_success_at ? timeAgo(connector.last_success_at) : "never"}
        {" · "}scopes {(manifest?.required_scopes ?? []).join(", ") || "local"}
        {resourceKey ? ` · ${resources.length} registered` : ""}
      </p>

      <div className="mt-3.5 flex flex-wrap items-center gap-x-4 gap-y-2.5 border-t border-line-row pt-3.5">
        <label className="flex items-center gap-2 text-[12.5px] text-muted">
          enabled
          <Switch checked={connector.enabled} label={`${connector.name} enabled`}
                  onChange={(v) => patch.mutate({ enabled: v })} />
        </label>
        <label className="flex items-center gap-2 text-[12.5px] text-muted">
          read-only
          <Switch checked={connector.mode === "read_only"} label={`${connector.name} read-only`}
                  onChange={(v) => patch.mutate({ mode: v ? "read_only" : "read_write" })} />
        </label>
        <div className="ml-auto flex shrink-0 items-center gap-3.5">
          {resourceKey ? (
            <button type="button" onClick={() => setManageOpen(true)}
                    className={cn(monoLink, "text-muted-2 hover:text-ink")}>
              MANAGE
            </button>
          ) : null}
          <button type="button" onClick={() => setToolsOpen(true)}
                  className={cn(monoLink, "text-accent hover:text-accent-hover")}>
            TOOLS
          </button>
          <button type="button" onClick={() => check.mutate()} disabled={check.isPending}
                  aria-label={`Check ${connector.name} health`}
                  className={cn(monoLink, "text-accent hover:text-accent-hover")}>
            {check.isPending ? (
              <span aria-hidden
                    className="block size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              <RefreshCw aria-hidden className="size-3.5" />
            )}
          </button>
        </div>
      </div>
      <ToolsDialog slug={connector.slug} name={connector.name} open={toolsOpen}
                   onClose={() => setToolsOpen(false)} />
      {resourceKey ? (
        <ManageResourcesDialog slug={connector.slug} name={connector.name} resourceKey={resourceKey}
                               resources={resources} open={manageOpen}
                               onClose={() => setManageOpen(false)} />
      ) : null}
    </Card>
  );
}

function ManageResourcesDialog({ slug, name, resourceKey, resources, open, onClose }: {
  slug: string; name: string; resourceKey: "webhooks" | "servers";
  resources: any[]; open: boolean; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: (resourceName: string) => api.removeConnectorResource(slug, resourceName),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["connectors"] }),
  });
  const noun = resourceKey === "webhooks" ? "webhook" : "server";
  return (
    <Dialog open={open} onClose={onClose} title={`${name} — registered ${resourceKey}`} wide>
      {resources.length === 0 ? (
        <p className="text-sm text-muted">
          No {resourceKey} registered yet. Use “Add MCP / n8n” to register one.
        </p>
      ) : (
        <ul className="space-y-2">
          {resources.map((r) => (
            <li key={r.name}
                className="flex items-center justify-between gap-3 rounded-[11px] border border-line-row bg-tile px-4 py-3">
              <div className="min-w-0">
                <p className="font-mono text-[12.5px] text-ink-soft">{r.name}</p>
                <p className="truncate text-[12px] text-muted">
                  {r.url || r.command || r.transport || noun}
                  {r.read_only ? " · read-only" : ""}
                  {r.discovered_tools ? ` · ${r.discovered_tools.length} tools` : ""}
                </p>
                {r.discovery_error ? (
                  <p className="text-[11.5px] text-danger">discovery: {r.discovery_error}</p>
                ) : null}
              </div>
              <Button size="sm" variant="ghost" busy={remove.isPending}
                      aria-label={`Remove ${r.name}`} onClick={() => remove.mutate(r.name)}>
                <Trash2 className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}

function ToolsDialog({ slug, name, open, onClose }: {
  slug: string; name: string; open: boolean; onClose: () => void;
}) {
  const { data: tools } = useQuery({
    queryKey: ["connector-tools", slug],
    queryFn: () => api.connectorTools(slug),
    enabled: open,
  });
  return (
    <Dialog open={open} onClose={onClose} title={`${name} — tools`} wide>
      {!tools ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : tools.length === 0 ? (
        <p className="text-sm text-muted">
          No tools yet. Register a webhook/server, or configure this connector.
        </p>
      ) : (
        <ul className="space-y-2">
          {tools.map((tool) => (
            <li key={tool.tool_id}
                className="flex items-center justify-between gap-3 rounded-[11px] border border-line-row bg-tile px-4 py-3">
              <div className="min-w-0">
                <p className="font-mono text-[12.5px] text-ink-soft">{tool.tool_id}</p>
                <p className="mt-0.5 text-[12px] text-muted">{tool.name}</p>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                {!tool.trusted ? (
                  <Badge tone="warn" title="User-registered — always needs your approval">
                    approval
                  </Badge>
                ) : null}
                {tool.external_side_effects ? <Badge tone="warn">external</Badge> : null}
                <RiskBadge risk={tool.risk_level} />
                {!tool.enabled ? <Badge tone="danger">off</Badge> : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}

function AddResourceDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<"mcp_server" | "n8n_webhook">("mcp_server");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [command, setCommand] = useState("");
  const [secretEnv, setSecretEnv] = useState("");
  const [readOnly, setReadOnly] = useState(false);

  const register = useMutation({
    mutationFn: () =>
      api.registerConnector(
        kind === "mcp_server"
          ? { kind, name, transport: command ? "stdio" : "inproc", command: command || undefined }
          : { kind, name, url, secret_env: secretEnv || undefined, read_only: readOnly,
              supports_dry_run: true },
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["connectors"] });
      onClose();
    },
  });

  return (
    <Dialog open={open} onClose={onClose} title="Add integration resource">
      <div className="space-y-4">
        <Field label="Type">
          <Select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} className="w-full">
            <option value="mcp_server">MCP server</option>
            <option value="n8n_webhook">n8n webhook</option>
          </Select>
        </Field>
        <p className="rounded-[11px] border border-(--warn-border) bg-warn-surface px-4 py-3 text-[12.5px] leading-relaxed text-muted">
          Tools you register here are{" "}
          <strong className="font-semibold text-warn">untrusted</strong>: every call needs your
          approval, even if labeled read-only. To let one run automatically, add an allow rule in
          Settings → Policies.
        </p>
        <Field label="Name" hint="Letters, numbers, dashes and underscores.">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="my-tools" />
        </Field>
        {kind === "mcp_server" ? (
          <Field label="stdio command (optional)"
                 hint="Leave empty to register the built-in in-process demo server. Discovered tools default to approval-required.">
            <Input value={command} onChange={(e) => setCommand(e.target.value)}
                   placeholder="npx -y @modelcontextprotocol/server-filesystem /path" />
          </Field>
        ) : (
          <>
            <Field label="Webhook URL">
              <Input value={url} onChange={(e) => setUrl(e.target.value)}
                     placeholder="https://your-n8n/webhook/…" />
            </Field>
            <Field label="HMAC secret name (recommended)"
                   hint="Name of a secret (e.g. COCKPIT_N8N_SECRET_MYFLOW). Add its value under Secrets above; it never enters the database.">
              <Input value={secretEnv} onChange={(e) => setSecretEnv(e.target.value)}
                     placeholder="COCKPIT_N8N_SECRET_MYFLOW" />
            </Field>
            <div className="flex items-center justify-between gap-3">
              <span className="text-[13px]">Read-only workflow (no external side effects)</span>
              <Switch checked={readOnly} onChange={setReadOnly} label="Read-only workflow" />
            </div>
          </>
        )}
        {register.isError ? <ErrorState detail={(register.error as Error).message} /> : null}
        <Button variant="primary" className="w-full" busy={register.isPending}
                disabled={!name.trim() || (kind === "n8n_webhook" && !url.trim())}
                onClick={() => register.mutate()}>
          Register
        </Button>
      </div>
    </Dialog>
  );
}
