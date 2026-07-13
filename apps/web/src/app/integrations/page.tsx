"use client";

// Integrations: pick a reasoning provider + model, manage API keys (write-only, local file),
// and add/edit/remove connectors (MCP servers, n8n webhooks). The policy gateway still decides
// what may actually run; mocked services are labeled until genuinely connected.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Connector, ProviderInfo, SecretSlot } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { CardSkeleton, ErrorState } from "@/components/ui/states";
import { Cpu, KeyRound, Plug, Plus, RefreshCw, Trash2 } from "lucide-react";

const HEALTH_TONE: Record<string, "accent" | "warn" | "danger" | "muted"> = {
  ok: "accent", mock: "warn", degraded: "warn", unavailable: "danger", unknown: "muted",
};
// Connectors whose registered resources (webhooks / servers) can be listed & removed.
const RESOURCE_KEY: Record<string, "webhooks" | "servers"> = { n8n: "webhooks", mcp: "servers" };

export default function IntegrationsPage() {
  const [addOpen, setAddOpen] = useState(false);
  const { data: connectors, isLoading, error, refetch } = useQuery({
    queryKey: ["connectors"], queryFn: api.connectors,
  });

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Integrations</h1>
          <p className="text-[13px] text-muted">
            Choose who does the thinking, add the keys that unlock services, and wire up the tools
            Otto can use. The policy gateway still gates every real action.
          </p>
        </div>
        <Button variant="primary" onClick={() => setAddOpen(true)}>
          <Plus className="size-4" /> Add MCP / n8n
        </Button>
      </header>

      <ProviderCard />
      <SecretsCard />

      <div>
        <h2 className="mb-2 mt-6 text-[13px] font-semibold uppercase tracking-wide text-muted">
          Connectors
        </h2>
        {isLoading ? (
          <CardSkeleton lines={6} />
        ) : error ? (
          <ErrorState detail={(error as Error).message} onRetry={() => refetch()} />
        ) : (
          <div className="grid gap-3 md:grid-cols-2" data-testid="connector-grid">
            {(connectors ?? []).map((connector) => (
              <ConnectorCard key={connector.slug} connector={connector} />
            ))}
          </div>
        )}
      </div>
      <AddResourceDialog open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}

// ------------------------------------------------------------------ providers

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
    <Card>
      <CardHeader title="Reasoning provider"
                  subtitle="Who does the thinking. Everything runs locally except calls to the provider you pick." />
      <CardBody className="space-y-3">
        {isLoading ? (
          <CardSkeleton lines={3} />
        ) : error || !data ? (
          <ErrorState detail={(error as Error)?.message} onRetry={() => refetch()} />
        ) : (
          <>
            <div className="grid gap-2 sm:grid-cols-2" data-testid="provider-grid">
              {data.providers.map((p) => (
                <button key={p.id} type="button"
                        onClick={() => patch.mutate({ provider: p.id, model: "" })}
                        aria-pressed={data.selected_provider === p.id}
                        className={cn(
                          "flex items-start justify-between gap-3 rounded-[10px] border px-3.5 py-2.5 text-left transition",
                          data.selected_provider === p.id
                            ? "border-accent bg-accent-soft/50"
                            : "border-line bg-raised hover:border-accent/50",
                        )}>
                  <div className="min-w-0">
                    <p className="flex items-center gap-1.5 text-[13.5px] font-medium">
                      <Cpu className="size-3.5 text-muted" /> {p.name}
                      <span className="text-[11px] font-normal text-muted">· {p.kind}</span>
                    </p>
                    <p className="mt-0.5 line-clamp-2 text-[12px] text-muted">{p.detail}</p>
                  </div>
                  <Badge tone={p.available ? "accent" : p.id === "mock" ? "muted" : "danger"}>
                    {p.available ? "ready" : "needs setup"}
                  </Badge>
                </button>
              ))}
            </div>
            <ProviderConfig
              provider={data.providers.find((p) => p.id === data.selected_provider)}
              selectedModel={data.selected_model}
              onModel={(model) => patch.mutate({ model })}
              onSaved={invalidate}
            />
          </>
        )}
      </CardBody>
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
    <div className="space-y-3 rounded-[10px] border border-line bg-surface px-3.5 py-3">
      {needsKey ? (
        <InlineSecret name={provider.requires_secret!} label={`${provider.name} API key`}
                      hint="Stored in a local, gitignored file (data/local/secrets.env) — never in the database or logs."
                      onSaved={onSaved} />
      ) : provider.requires_secret ? (
        <p className="text-[12.5px] text-muted">
          <KeyRound className="mr-1 inline size-3.5" />
          {provider.requires_secret} is configured. Manage it under Secrets below.
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
  const { data, isLoading } = useQuery({ queryKey: ["secrets"], queryFn: api.secrets });
  return (
    <Card>
      <CardHeader title="Secrets"
                  subtitle="API keys and webhook secrets. Values are write-only — saved to a local 0600 file, never shown back, never committed or logged." />
      <CardBody className="space-y-2">
        {isLoading ? (
          <CardSkeleton lines={3} />
        ) : (
          (data?.secrets ?? []).map((slot) => <SecretRow key={slot.name} slot={slot} />)
        )}
      </CardBody>
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
    <div className="rounded-[10px] border border-line bg-raised px-3.5 py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-mono text-[12.5px]">{slot.name}
            {slot.configured
              ? <Badge tone={slot.source === "env" ? "outline" : "accent"}>
                  {slot.source === "env" ? "from environment" : "set"}
                </Badge>
              : <Badge tone="muted">not set</Badge>}
          </p>
          <p className="mt-0.5 text-[12px] text-muted">{slot.description}</p>
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
        <p className="mt-1 text-[11.5px] text-muted">
          Set in your shell environment — it overrides any value saved here. Unset it there to change it.
        </p>
      ) : null}
      {editing ? (
        <div className="mt-2">
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
    <Card className={cn(!connector.enabled && "opacity-60")} data-testid={`connector-${connector.slug}`}>
      <CardBody className="flex h-full flex-col gap-2.5 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded-[9px] bg-accent-soft text-accent">
              <Plug className="size-4" />
            </span>
            <div>
              <p className="text-[14.5px] font-semibold">{connector.name}</p>
              <p className="text-[11.5px] text-muted">{connector.category}</p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <Badge tone={HEALTH_TONE[connector.health] ?? "muted"}>{connector.health}</Badge>
            {isMock ? <Badge tone="outline">mock — demo data</Badge> : null}
          </div>
        </div>

        <p className="text-[12.5px] text-muted">{connector.health_detail || manifest?.description}</p>
        <p className="text-[11.5px] text-muted">
          last ok: {connector.last_success_at ? timeAgo(connector.last_success_at) : "never"}
          {resourceKey ? ` · ${resources.length} registered` : ""}
          {" · "}scopes: {(manifest?.required_scopes ?? []).join(", ") || "local"}
        </p>

        <div className="mt-auto flex flex-wrap items-center gap-3 border-t border-line pt-2.5">
          <label className="flex items-center gap-1.5 text-[12px] text-muted">
            enabled
            <Switch checked={connector.enabled} label={`${connector.name} enabled`}
                    onChange={(v) => patch.mutate({ enabled: v })} />
          </label>
          <label className="flex items-center gap-1.5 text-[12px] text-muted">
            read-only
            <Switch checked={connector.mode === "read_only"} label={`${connector.name} read-only`}
                    onChange={(v) => patch.mutate({ mode: v ? "read_only" : "read_write" })} />
          </label>
          <div className="ml-auto flex gap-1.5">
            {resourceKey ? (
              <Button size="sm" variant="ghost" onClick={() => setManageOpen(true)}>Manage</Button>
            ) : null}
            <Button size="sm" variant="ghost" onClick={() => setToolsOpen(true)}>Tools</Button>
            <Button size="sm" busy={check.isPending} onClick={() => check.mutate()}
                    aria-label={`Check ${connector.name} health`}>
              <RefreshCw className="size-3.5" />
            </Button>
          </div>
        </div>
        <ToolsDialog slug={connector.slug} name={connector.name} open={toolsOpen}
                     onClose={() => setToolsOpen(false)} />
        {resourceKey ? (
          <ManageResourcesDialog slug={connector.slug} name={connector.name} resourceKey={resourceKey}
                                 resources={resources} open={manageOpen}
                                 onClose={() => setManageOpen(false)} />
        ) : null}
      </CardBody>
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
                className="flex items-center justify-between gap-3 rounded-[10px] border border-line bg-raised px-3.5 py-2.5">
              <div className="min-w-0">
                <p className="font-mono text-[12.5px]">{r.name}</p>
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
                className="flex items-center justify-between gap-3 rounded-[10px] border border-line bg-raised px-3.5 py-2.5">
              <div className="min-w-0">
                <p className="font-mono text-[12.5px]">{tool.tool_id}</p>
                <p className="text-[12px] text-muted">{tool.name}</p>
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
        <p className="rounded-[10px] border border-line bg-raised px-3 py-2 text-[12px] text-muted">
          Tools you register here are <strong>untrusted</strong>: every call needs your approval,
          even if labeled read-only. To let one run automatically, add an allow rule in
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
            <div className="flex items-center justify-between">
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
