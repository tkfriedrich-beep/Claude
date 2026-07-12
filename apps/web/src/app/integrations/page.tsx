"use client";

// Connector registry: health, mode, tools; register MCP servers & n8n webhooks.
// Mock connectors are labeled honestly until genuinely configured.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Connector } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { CardSkeleton, ErrorState } from "@/components/ui/states";
import { Plug, Plus, RefreshCw } from "lucide-react";

const HEALTH_TONE: Record<string, "accent" | "warn" | "danger" | "muted"> = {
  ok: "accent", mock: "warn", degraded: "warn", unavailable: "danger", unknown: "muted",
};

export default function IntegrationsPage() {
  const [addOpen, setAddOpen] = useState(false);
  const { data: connectors, isLoading, error, refetch } = useQuery({
    queryKey: ["connectors"], queryFn: api.connectors,
  });
  const { data: settings } = useQuery({ queryKey: ["settings"], queryFn: api.settings });

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Integrations</h1>
          <p className="text-[13px] text-muted">
            Connectors expose tools; the policy gateway decides what may run. Mocked services
            are labeled until genuinely connected.
          </p>
        </div>
        <Button variant="primary" onClick={() => setAddOpen(true)}>
          <Plus className="size-4" /> Add MCP / n8n
        </Button>
      </header>

      {/* provider status */}
      {settings ? (
        <Card>
          <CardBody className="pt-4">
            <p className="mb-2 text-[13px] font-semibold uppercase tracking-wide text-muted">
              Reasoning providers
            </p>
            <ul className="grid gap-2 sm:grid-cols-2">
              {Object.entries(settings.providers).map(([name, info]) => (
                <li key={name} className="flex items-start justify-between gap-3 rounded-[10px] border border-line bg-raised px-3.5 py-2.5">
                  <div>
                    <p className="text-[13.5px] font-medium capitalize">{name}</p>
                    <p className="text-[12px] text-muted">{info.detail}</p>
                  </div>
                  <Badge tone={info.available ? "accent" : "muted"}>
                    {info.available ? "available" : name === "mock" ? "" : "unavailable"}
                  </Badge>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

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
      <AddResourceDialog open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}

function ConnectorCard({ connector }: { connector: Connector }) {
  const queryClient = useQueryClient();
  const [toolsOpen, setToolsOpen] = useState(false);
  const manifest = connector.manifest as Record<string, any>;
  const isMock = Boolean(manifest?.mock);

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
            <Button size="sm" variant="ghost" onClick={() => setToolsOpen(true)}>Tools</Button>
            <Button size="sm" busy={check.isPending} onClick={() => check.mutate()}
                    aria-label={`Check ${connector.name} health`}>
              <RefreshCw className="size-3.5" />
            </Button>
          </div>
        </div>
        <ToolsDialog slug={connector.slug} name={connector.name} open={toolsOpen}
                     onClose={() => setToolsOpen(false)} />
      </CardBody>
    </Card>
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
            <Field label="HMAC secret env var (recommended)"
                   hint="Name of an environment variable (e.g. COCKPIT_N8N_SECRET_MYFLOW). The value never enters the database.">
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
