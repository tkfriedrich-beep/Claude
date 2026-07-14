"use client";

// Agent detail (/skills/[slug]): mandate, the autonomy ladder (each step is the same
// PATCH the old select issued — explicit act, never automatic), risk grant, enabled
// switch, manifest details, run form. Same skill registry, same endpoints.
import { use, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { handleRadioKeys } from "@/lib/a11y";
import { AUTONOMY_LABEL, RISK_LABEL } from "@/lib/types";
import { RiskBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Select, Textarea } from "@/components/ui/input";
import { agentMetaFor, Monogram } from "@/components/ui/monogram";
import { Switch } from "@/components/ui/switch";
import { CardSkeleton, ErrorState, SectionLabel } from "@/components/ui/states";
import { cn } from "@/lib/utils";
import { Play } from "lucide-react";

const AUTONOMY_STEPS = [0, 1, 2, 3, 4, 5];

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
  const autonomyBtns = useRef<(HTMLButtonElement | null)[]>([]);

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

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-5">
        <CardSkeleton lines={6} />
        <CardSkeleton lines={4} />
      </div>
    );
  }
  if (error || !skill) {
    return (
      <div className="mx-auto max-w-3xl">
        <ErrorState title="Agent not found" detail={(error as Error)?.message} onRetry={() => refetch()} />
      </div>
    );
  }

  const meta = agentMetaFor(skill.slug, skill.name);
  const manifest = skill.manifest as Record<string, any>;
  const requiredInput: string[] = manifest?.input_schema?.required ?? [];
  const example =
    slug === "decision-memo"
      ? '{\n  "decision": "…?",\n  "options": [{"name": "A"}, {"name": "B"}],\n  "context": "…"\n}'
      : slug === "research-run"
        ? '{ "question": "…" }'
        : "{}";

  return (
    <div className="fadeup mx-auto max-w-3xl space-y-5">
      <header className="flex flex-wrap items-start gap-4">
        <Monogram initials={meta.mono} state={skill.enabled ? "idle" : "blocked"} size={52} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-[22px] font-semibold tracking-[-0.02em]">{meta.name}</h1>
            <RiskBadge risk={skill.risk_level} />
          </div>
          <p className="mt-1 font-mono text-[11.5px] tracking-[0.04em] text-muted-2">
            {skill.slug} · v{skill.version}
          </p>
          <p className="mt-3 max-w-xl text-[14px] leading-relaxed text-muted">{skill.description}</p>
        </div>
      </header>

      <Card>
        <CardHeader title="Grant & controls"
                    subtitle="Autonomy changes are always your explicit act — never automatic." />
        <CardBody className="space-y-6">
          <div>
            <SectionLabel>Autonomy — graduated, per agent</SectionLabel>
            {/* The ladder replaces the old select; each step issues the identical PATCH. */}
            <div role="radiogroup" aria-label="Autonomy level" data-testid="autonomy-select"
                 className="mt-3 flex flex-wrap gap-1.5">
              {AUTONOMY_STEPS.map((level, i) => {
                const active = skill.autonomy === level;
                const setLevel = (index: number) => {
                  const target = AUTONOMY_STEPS[index];
                  autonomyBtns.current[index]?.focus();
                  if (target !== skill.autonomy) patch.mutate({ autonomy: target });
                };
                return (
                  <button
                    key={level}
                    ref={(el) => { autonomyBtns.current[i] = el; }}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    tabIndex={active ? 0 : -1}
                    disabled={patch.isPending}
                    onClick={() => { if (!active) patch.mutate({ autonomy: level }); }}
                    onKeyDown={(e) => handleRadioKeys(e, AUTONOMY_STEPS.length, skill.autonomy, setLevel)}
                    className={cn(
                      "rounded-full border px-3.5 py-[5px] font-mono text-[10.5px] font-medium",
                      "uppercase tracking-[0.08em] transition-colors",
                      active
                        ? "border-(--accent-border) bg-accent-soft text-accent-hover"
                        : "border-line-control text-muted-2 hover:border-faint hover:text-ink",
                      patch.isPending && "opacity-60",
                    )}
                  >
                    {AUTONOMY_LABEL[level] ?? `Level ${level}`}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            <Switch checked={skill.enabled} label="Skill enabled"
                    onChange={(v) => patch.mutate({ enabled: v })} />
            <span className="text-[13px] text-muted">{skill.enabled ? "Enabled" : "Disabled"}</span>
          </div>

          <dl className="grid gap-x-7 gap-y-4 border-t border-line-row pt-5 sm:grid-cols-2">
            <div>
              <dt className="section-label">Risk grant</dt>
              <dd className="mt-1.5 text-[13.5px]">
                {skill.risk_level}
                {RISK_LABEL[skill.risk_level] ? ` — ${RISK_LABEL[skill.risk_level]}` : ""}
              </dd>
            </div>
            <div>
              <dt className="section-label">Version</dt>
              <dd className="mt-1.5 font-mono text-[12.5px]">v{skill.version}</dd>
            </div>
            <div>
              <dt className="section-label">Allowed tools</dt>
              <dd className="mt-1.5 font-mono text-[12px]">
                {(manifest.allowed_tools ?? []).join(", ") || "none — pure composition"}
              </dd>
            </div>
            <div>
              <dt className="section-label">Required connectors</dt>
              <dd className="mt-1.5 text-[13.5px]">
                {(manifest.required_connectors ?? []).join(", ") || "none"}
              </dd>
            </div>
            <div>
              <dt className="section-label">Domains</dt>
              <dd className="mt-1.5 text-[13.5px]">{(skill.domains ?? []).join(", ")}</dd>
            </div>
            <div>
              <dt className="section-label">Limits</dt>
              <dd className="mt-1.5 text-[13.5px]">
                {manifest.timeout_seconds}s · max {manifest.max_steps} tool calls
              </dd>
            </div>
            <div>
              <dt className="section-label">Schedulable</dt>
              <dd className="mt-1.5 text-[13.5px]">
                {manifest.supports_schedule ? "Yes (Shadow Mode available)" : "No"}
              </dd>
            </div>
            <div>
              <dt className="section-label">Verification</dt>
              <dd className="mt-1.5 font-mono text-[12px]">
                {(manifest.verification_rules ?? []).join(" · ")}
              </dd>
            </div>
          </dl>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Run now" />
        <CardBody className="space-y-4">
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
