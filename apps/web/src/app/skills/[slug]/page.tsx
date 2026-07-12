"use client";

// Skill detail: purpose, required data, tools, risk, autonomy control, run form.
import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AUTONOMY_LABEL } from "@/lib/types";
import { Badge, RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Select, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { CardSkeleton, ErrorState } from "@/components/ui/states";
import { Play } from "lucide-react";

export default function SkillDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: skill, isLoading, error, refetch } = useQuery({
    queryKey: ["skill", slug],
    queryFn: () => api.skill(slug),
  });
  const [mode, setMode] = useState("draft");
  const [inputJson, setInputJson] = useState("");
  const [inputError, setInputError] = useState<string | null>(null);

  const patch = useMutation({
    mutationFn: (body: { autonomy?: number; enabled?: boolean }) => api.patchSkill(slug, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["skill", slug] });
      queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });
  const run = useMutation({
    mutationFn: () => {
      let input: Record<string, unknown> = {};
      if (inputJson.trim()) {
        try {
          input = JSON.parse(inputJson);
        } catch {
          throw new Error("Input is not valid JSON.");
        }
      }
      return api.runSkill(slug, { input, mode });
    },
    onSuccess: (r) => router.push(`/history/${r.id}`),
    onError: (e: Error) => setInputError(e.message),
  });

  if (isLoading) return <div className="mx-auto max-w-3xl"><CardSkeleton lines={6} /></div>;
  if (error || !skill) {
    return (
      <div className="mx-auto max-w-3xl">
        <ErrorState title="Skill not found" detail={(error as Error)?.message} onRetry={() => refetch()} />
      </div>
    );
  }

  const manifest = skill.manifest as Record<string, any>;
  const requiredInput: string[] = manifest?.input_schema?.required ?? [];
  const example =
    slug === "decision-memo"
      ? '{\n  "decision": "…?",\n  "options": [{"name": "A"}, {"name": "B"}],\n  "context": "…"\n}'
      : slug === "research-run"
        ? '{ "question": "…" }'
        : "{}";

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight">{skill.name}</h1>
          <p className="mt-0.5 max-w-xl text-[13.5px] text-muted">{skill.description}</p>
        </div>
        <div className="flex items-center gap-2">
          <RiskBadge risk={skill.risk_level} />
          <Badge tone="outline">v{skill.version}</Badge>
        </div>
      </header>

      <Card>
        <CardHeader title="Grant & controls"
                    subtitle="Autonomy changes are always your explicit act — never automatic." />
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-center gap-4">
            <Field label="Autonomy">
              <Select
                value={skill.autonomy}
                onChange={(e) => patch.mutate({ autonomy: Number(e.target.value) })}
                aria-label="Autonomy level"
                data-testid="autonomy-select"
              >
                {[0, 1, 2, 3, 4, 5].map((level) => (
                  <option key={level} value={level}>{AUTONOMY_LABEL[level]}</option>
                ))}
              </Select>
            </Field>
            <div className="flex items-center gap-2 pt-5">
              <Switch checked={skill.enabled} label="Skill enabled"
                      onChange={(v) => patch.mutate({ enabled: v })} />
              <span className="text-[13px] text-muted">{skill.enabled ? "Enabled" : "Disabled"}</span>
            </div>
          </div>
          <dl className="grid gap-x-6 gap-y-1.5 text-[13px] sm:grid-cols-2">
            <div>
              <dt className="font-medium text-muted">Allowed tools</dt>
              <dd className="font-mono text-[12px]">
                {(manifest.allowed_tools ?? []).join(", ") || "none — pure composition"}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-muted">Required connectors</dt>
              <dd>{(manifest.required_connectors ?? []).join(", ") || "none"}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted">Domains</dt>
              <dd>{(skill.domains ?? []).join(", ")}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted">Limits</dt>
              <dd>{manifest.timeout_seconds}s · max {manifest.max_steps} tool calls</dd>
            </div>
            <div>
              <dt className="font-medium text-muted">Schedulable</dt>
              <dd>{manifest.supports_schedule ? "Yes (Shadow Mode available)" : "No"}</dd>
            </div>
            <div>
              <dt className="font-medium text-muted">Verification</dt>
              <dd className="font-mono text-[12px]">{(manifest.verification_rules ?? []).join(" · ")}</dd>
            </div>
          </dl>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Run now" />
        <CardBody className="space-y-3">
          <Field label="Execution mode" hint="Draft never mutates anything external; Act asks for approval where policy requires it.">
            <Select value={mode} onChange={(e) => setMode(e.target.value)} aria-label="Execution mode">
              <option value="read_only">Read-only</option>
              <option value="draft">Draft</option>
              <option value="act">Act</option>
            </Select>
          </Field>
          {requiredInput.length > 0 ? (
            <Field label={`Input JSON (required: ${requiredInput.join(", ")})`}>
              <Textarea rows={6} value={inputJson} onChange={(e) => setInputJson(e.target.value)}
                        placeholder={example} className="font-mono text-[12.5px]"
                        data-testid="skill-input-json" />
            </Field>
          ) : null}
          {inputError ? <ErrorState title="Cannot run" detail={inputError} /> : null}
          <Button variant="primary" busy={run.isPending} disabled={!skill.enabled}
                  onClick={() => { setInputError(null); run.mutate(); }} data-testid="skill-run-btn">
            <Play className="size-4" /> Run {skill.name}
          </Button>
        </CardBody>
      </Card>
    </div>
  );
}
