# Business Idea Triage

**Purpose.** Turn a folder of half-written idea notes into a ranked scorecard with one concrete
next validation action per idea.

**Required data.** The configured `bizideas` folder (onboarding/Settings → Storage; the demo
folder works out of the box). One idea per `*.md`/`*.txt` file.

**How it works.** Heuristic keyword-density scoring (1–5) across problem clarity, market,
monetization, moat, and validation — deliberately simple and stated as such in every scorecard.
The weakest dimension drives the suggested next action.

**Writes are approval-gated.** Source files are never modified. The skill *proposes* writing
`<idea>.scorecard.md` next to each idea via `local_files.write` (approval required; diff
preview shown). In draft/shadow mode the write becomes a dry-run preview. A denial is recorded
as "skipped" and the triage still completes.

**Risk & autonomy.** R2 (local reversible writes, each individually approved). Default
autonomy: Draft.

**Output.** `idea-triage.md` + `idea-triage.json`; unresolved list carries skipped write-backs.

**Verification.** Markdown artifact exists · sources non-empty · JSON validates ·
`no_unconfirmed_success` (no unconfirmed external effects).
