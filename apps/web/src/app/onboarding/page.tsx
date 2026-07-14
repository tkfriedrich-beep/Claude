"use client";

// Onboarding: name Otto, choose data locations, provider, Safe Mode, demo data.
// OttoOS retoken only — flow, fields, defaults, and testids are unchanged.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { OttoPulse } from "@/components/cockpit/otto-pulse";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { ErrorState } from "@/components/ui/states";
import { AUTONOMY_LABEL } from "@/lib/types";

export default function OnboardingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    user_name: "",
    assistant_name: "Otto",
    vault_path: "",
    bizideas_path: "",
    enable_demo_data: true,
    safe_mode: true,
    default_autonomy: 3,
    provider: "mock" as "mock" | "claude",
  });
  const { data: settings } = useQuery({ queryKey: ["settings-preflight"],
    queryFn: api.settings, retry: 0, enabled: step === 2, });

  const submit = useMutation({
    mutationFn: () =>
      api.onboard({
        ...form,
        vault_path: form.vault_path || null,
        bizideas_path: form.bizideas_path || null,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      router.replace("/");
    },
  });

  const steps = ["You & Otto", "Your data", "Provider & safety"];

  return (
    <div className="fadeup mx-auto flex min-h-dvh max-w-xl flex-col justify-center px-5 py-10">
      <div className="mb-7 flex flex-col items-center text-center">
        <OttoPulse state="idle" size={92} showLabel={false} />
        <p className="mt-4 font-mono text-[11px] font-medium uppercase tracking-[2.5px] text-accent">
          First-run setup
        </p>
        <h1 className="otto-voice mt-2 text-[30px] font-medium leading-[1.15] text-ink">
          Welcome to OttoOS.
        </h1>
        <p className="mt-2.5 max-w-md text-[14px] leading-relaxed text-muted">
          Local-first. Your data stays on this machine; nothing external runs without approval.
        </p>
      </div>

      <nav aria-label="Progress" className="mb-5 flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5">
        {steps.map((label, i) => (
          <span
            key={label}
            aria-current={i === step ? "step" : undefined}
            className={cn(
              "font-mono text-[10.5px] font-medium uppercase tracking-[2.5px]",
              i === step ? "text-accent" : i < step ? "text-muted" : "text-faint",
            )}
          >
            {String(i + 1).padStart(2, "0")} · {label}
          </span>
        ))}
      </nav>

      <Card>
        <CardBody className="pt-5">
          <div key={step} className="fadeup space-y-4">
            {step === 0 ? (
              <>
                <Field label="Your name">
                  <Input
                    data-testid="ob-name"
                    value={form.user_name}
                    onChange={(e) => setForm({ ...form, user_name: e.target.value })}
                    placeholder="e.g. Alex"
                    autoFocus
                  />
                </Field>
                <Field label="Assistant name" hint="Otto by default — rename freely.">
                  <Input
                    value={form.assistant_name}
                    onChange={(e) => setForm({ ...form, assistant_name: e.target.value })}
                  />
                </Field>
              </>
            ) : null}

            {step === 1 ? (
              <>
                <Field
                  label="Obsidian vault path (optional)"
                  hint="Read-only until you approve writes. Leave empty to use the demo vault."
                >
                  <Input
                    value={form.vault_path}
                    onChange={(e) => setForm({ ...form, vault_path: e.target.value })}
                    placeholder="/Users/you/Obsidian/MainVault"
                  />
                </Field>
                <Field
                  label="Business ideas folder (optional)"
                  hint="For Business Idea Triage — e.g. ~/Desktop/bizideas. Demo folder used if empty."
                >
                  <Input
                    value={form.bizideas_path}
                    onChange={(e) => setForm({ ...form, bizideas_path: e.target.value })}
                    placeholder="/Users/you/Desktop/bizideas"
                  />
                </Field>
                <div className="flex items-center justify-between gap-4 rounded-[11px] border border-line-control bg-tile px-4 py-3">
                  <div>
                    <p className="text-[13.5px] font-medium text-ink">Include demo data</p>
                    <p className="mt-0.5 text-[12.5px] text-muted">
                      Realistic sample vault, ideas, agenda — clearly labeled, removable anytime.
                    </p>
                  </div>
                  <Switch
                    checked={form.enable_demo_data}
                    onChange={(v) => setForm({ ...form, enable_demo_data: v })}
                    label="Include demo data"
                  />
                </div>
              </>
            ) : null}

            {step === 2 ? (
              <>
                <Field label="Reasoning provider" hint="Demo runtime works offline with zero credentials. Claude uses ANTHROPIC_API_KEY or your authenticated claude CLI.">
                  <Select
                    value={form.provider}
                    onChange={(e) => setForm({ ...form, provider: e.target.value as "mock" | "claude" })}
                    className="w-full"
                  >
                    <option value="mock">Demo runtime (no credentials needed)</option>
                    <option value="claude">
                      Claude {settings?.providers?.claude?.available === false ? "— not detected yet" : ""}
                    </option>
                  </Select>
                </Field>
                <Field label="Default autonomy for skills">
                  <Select
                    value={form.default_autonomy}
                    onChange={(e) => setForm({ ...form, default_autonomy: Number(e.target.value) })}
                    className="w-full"
                  >
                    {[1, 2, 3, 4].map((level) => (
                      <option key={level} value={level}>{AUTONOMY_LABEL[level]}</option>
                    ))}
                  </Select>
                </Field>
                <div className="flex items-center justify-between gap-4 rounded-[11px] border border-line-control bg-tile px-4 py-3">
                  <div>
                    <p className="text-[13.5px] font-medium text-ink">Safe Mode</p>
                    <p className="mt-0.5 text-[12.5px] text-muted">
                      Blocks all external writes globally. Recommended on. Toggle anytime.
                    </p>
                  </div>
                  <Switch
                    checked={form.safe_mode}
                    onChange={(v) => setForm({ ...form, safe_mode: v })}
                    label="Safe Mode"
                  />
                </div>
              </>
            ) : null}

            {submit.isError ? (
              <ErrorState title="Setup failed" detail={(submit.error as Error).message} />
            ) : null}
          </div>

          <div className="mt-5 flex justify-between border-t border-line-row pt-4">
            <Button variant="ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>
              Back
            </Button>
            {step < 2 ? (
              <Button
                variant="primary"
                data-testid="ob-next"
                disabled={step === 0 && !form.user_name.trim()}
                onClick={() => setStep(step + 1)}
              >
                Continue
              </Button>
            ) : (
              <Button
                variant="primary"
                data-testid="ob-finish"
                busy={submit.isPending}
                onClick={() => submit.mutate()}
              >
                Launch cockpit
              </Button>
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
