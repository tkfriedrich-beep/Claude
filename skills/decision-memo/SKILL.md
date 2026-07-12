# Decision Memo

**Purpose.** Force clarity on one decision: decision, context, options, evidence, assumptions,
trade-offs, recommendation with confidence, pre-mortem, review date.

**Required data.** Structured input — `decision` (string, required), `options` (≥2, each with
optional `notes`, `evidence`, `tradeoffs`), optional `context`, `criteria[]`, `assumptions[]`,
`risks[]`, `deadline`.

**How it works.** Deterministic composition from your input; if the Claude provider is
healthy, an "Analysis (Otto)" section is generated (prompt: `prompts/analysis_v1.md`) and the
artifact is labeled `llm_assisted`. Without a provider, the memo still ships and its
confidence is honestly capped at "low". No evidence is ever invented — missing input is shown
as missing.

**Risk & autonomy.** R2 (produces local artifacts only). No tool calls, no external effects.

**Output.** `decision-memo.md` + `decision-memo.json` artifacts.

**Verification.** Both artifacts exist · JSON validates against `output.schema.json`.
