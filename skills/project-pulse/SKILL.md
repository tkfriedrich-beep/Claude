# Project Pulse

**Purpose.** Answer "what moved, what's stuck, what's next?" across every project note in the
vault's `/projects` section — without you opening a single file.

**Required data.** An Obsidian vault (or the demo vault) with Markdown notes under
`/projects`. Frontmatter `status:` and checkbox tasks improve signal but aren't required.

**How it works.** Deterministic analysis: recent-edit detection (7-day window), open/done
checkbox counts, `blocked/waiting on` markers, `Next:` lines, staleness (≥10 days without
edits). No LLM required; no writes performed.

**Risk & autonomy.** R0 (local read-only). Default autonomy: Draft. Schedulable (works well in
Shadow Mode).

**Output.** Markdown report + JSON artifact; per-project source links; unresolved list carries
blocked items.

**Verification.** Markdown artifact exists · every project cites its source note · JSON output
validates against `output.schema.json`.
