# Adversarial code review — AgenticOS Cockpit / OttoOS — ROUND 4

You are a skeptical staff-level reviewer. Rounds 1–3 hit the **backend** (policy gateway, SSRF,
event store, idempotency) and found 6 + 12 + 13 real defects — all fixed. **This round is
different: the surface under review is the front end.** Two large, self-tested changes have never
been independently reviewed:

1. **Providers + secrets + editable integrations** (PR #7, merged) — `OpenAIAgentRuntime`,
   `OllamaAgentRuntime`, a file-backed `LocalSecretStore`, and the providers/secrets/connector-
   resource APIs.
2. **The OttoOS visual redesign** (this PR) — a champagne-gold "flight deck" reskin that rewrote
   **all 13 screens in parallel** plus the whole shell (nav, command band, ambient rail, work
   modes, ⌘K palette, decision card), under a hard **"nothing removed"** rule.

The redesign was produced by fanning out one AI agent per screen, each told "preserve every
control, query, testid, and honesty line." **That is exactly the process most likely to drop
something quietly.** Your job: prove a control, data path, safety affordance, or accessibility
guarantee regressed — or that a genuinely new client-side seam (the band→command autosubmit
handoff, work-mode state, rail inline-approve, keyboard `a`/`d`, write-only secret entry) is
broken. A review that only says "looks consistent" is a failed review; show what fell off.

Earn credit only for defects you can **demonstrate** (failing test, reproduction, or traced
path with `file:line`). No pure aesthetics — "this padding is 2px off" is out of scope unless it
breaks usability (overflow, unclickable, invisible text, contrast failure). Label every finding
**CONFIRMED** or **SUSPECTED**.

---

## 1. Repository & setup

- **Repo:** `github.com/tkfriedrich-beep/Claude`, branch `claude/build-brief-implementation-dbre2i`.
  Review at the current HEAD of that branch (the OttoOS redesign tip). PR: the "OttoOS visual
  redesign" PR (all 13 screens).
- **Read first, so you don't re-litigate settled decisions:**
  - `DECISIONS.md` **ADR-018** (providers/secrets/integrations) and **ADR-019** (OttoOS redesign —
    the preservation contract, the executive renames, and the deliberately-omitted spec slots).
  - `PROGRESS.md` M6 + M7.
  - The design source of truth (a handoff bundle): the redesign is a *presentation-layer* change —
    **routes, API calls, and behavior are supposed to be identical to before.** The renames are
    label-only: Home→Briefing, Projects→Missions, Skills→Agents, Approvals→Decisions,
    People→Relationships, Integrations→Systems, History→Archive, Agenda→Calendar. The URLs did
    **not** change.
  - The author's own tests — **assume they under-cover the redesign:** `apps/web` vitest specs,
    `apps/web/e2e/*.spec.ts` (updated only for renamed labels), and `services/control-plane/tests/
    test_providers_secrets.py`.
- **Build & run** (no Docker):
  ```bash
  make setup && make demo && make dev        # control plane :8787, web :3000
  cd apps/web && pnpm typecheck && pnpm lint && pnpm test -- --run && pnpm build
  cd apps/web && PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome \
    pnpm exec playwright test        # desktop + mobile, boots its own isolated control plane
  cd services/control-plane && uv run pytest -q
  ```
  Diff the redesign against the pre-OttoOS state to see exactly what each screen lost or moved:
  ```bash
  git log --oneline | grep -i ottoos     # find the 3 redesign commits + the merge base
  git diff <merge-base>..HEAD -- apps/web/src
  ```

**Out of scope:** backend rounds 1–3 findings (report only if a redesign re-opened one),
intentional mocks (Google/Notion/GitHub), the no-auth localhost API (documented single-user
decision), pure visual taste, and the spec slots ADR-019 explicitly defers (mission
progress/milestone/confidence, briefing synthesis grid, approvals Defer, deep-work agenda block —
these are *supposed* to be absent; do not report them as "missing features").

---

## 2. Primary target — preservation regressions in the 13-screen reskin

The core claim is **"nothing removed."** Falsify it. For each screen, diff old→new and prove a
user-facing capability is gone, dead, or silently changed. High-value hunting grounds:

- **Dropped controls / dead wiring.** A button that no longer calls its mutation; a `<Select>`
  whose `onChange` was lost; a filter tab that renders but doesn't filter; a form field that no
  longer maps to its `CommandRequest` / settings key. Especially:
  - **Command** (`/command`): the composer, mode selector, and every scope/context/budget/deadline
    control — do they still submit the same request? Is `command-composer` / `command-send` still
    wired? Does the NEW band→command handoff (`?prefill=…&mode=…&autosubmit=1` / `preview=1`) ever
    **double-submit**, submit on reload, or fire with a stale mode? Trace the submit-once guard.
  - **Settings** (`/settings`): Safe Mode, kill switch, default mode (now a segmented control —
    does it PATCH the same values?), provider select (does it still reset model?), theme, budgets
    (onBlur patch), memory review approve/reject, domain toggles, policy create/delete. Every one
    must still hit its endpoint.
  - **Systems** (`/integrations`): the PR-#7 features — provider selection, per-provider **model
    dropdown**, the **write-only secret entry** (prove the value is never rendered back into the
    DOM, never placed in an input's `value`, never logged), connector enable/read-only switches,
    Tools dialog, resource add/**remove**, health check. Did any survive as UI but lose its call?
  - **Agents** (`/skills` + `[slug]`): the autonomy **ladder** replaced a `<select>` — does
    clicking a step issue the exact same PATCH, and can you reach every autonomy level (0–5)?
  - **Decisions/Archive**: tabs/filters actually filter; run detail keeps interrupt/resume/cancel
    and the `Verification` / `Unresolved` text the e2e asserts.
- **Honesty-copy loss.** The app's trust model leans on verbatim disclosures: "demo" / "mock —
  demo data" labels, "nothing external runs without your approval", "an expired approval never
  executes", "Otto never promotes itself", the "Always allow lives only in Settings → Policies"
  footer, roadmap caveats. Grep the diff for any that vanished or weakened.
- **Fabricated data.** ADR-019 forbids inventing values. Find any screen that renders a
  hardcoded/prototype demo number (a fake progress %, a made-up confidence, a static "9 OK · 2
  MOCK" that isn't computed from the API) as if it were real. Trace it to its source.
- **testid / aria drift.** Any `data-testid` the e2e or vitest depends on that was renamed or
  dropped (the suite may pass because the *test* was also changed — check the change was
  label-only, not a weakened assertion). Any `aria-label`/role that regressed.

## 3. Second target — the new shell seams (never existed before)

- **Work modes** (`work-mode.tsx`): Focus/Deep collapse nav/rail via client state. Does Deep Work
  actually keep approvals reachable (it "queues silently" — but can you still get to `/approvals`)?
  Does `ESC` ever trap focus or eat a keystroke a form needed? Is the mode state leaking a stuck
  layout (nav width 0) that you can't recover from without a reload?
- **Command band** (`command-band.tsx`): it renders on every screen and fires 4 polling queries
  (runs/approvals/usage/connectors/settings). Any duplicate-fetch storm with the same queries in a
  page? Does the kill-switch/error orb state agree with Settings, or can they disagree?
- **Ambient rail inline-approve**: the rail approves/denies decisions with one click and hides the
  Approve button when a typed phrase is required — verify an R4 confirm-phrase decision can **never**
  be one-click approved from the rail, and that the mini-card path can't skip the gateway.
- **⌘K palette**: RUN actions execute a skill immediately. Any action that runs without the same
  gating as the page path? Does the palette's provider/model/safe-mode toggle stay in sync?
- **Decision card `a`/`d` keys**: prove they only fire when the card is focused (not while typing a
  note/confirm phrase), and that `a` cannot approve an R4 card whose phrase isn't satisfied.
- **Hydration / SSR**: dark is now the default via an inline pre-hydration script + `next/font`.
  Any hydration mismatch (the theme toggle bug was fixed once — did the redesign reintroduce one on
  any component reading `document`/`window`/`localStorage` during render)? Any `useSearchParams`
  without a `<Suspense>` boundary that breaks `next build` or first paint?

## 4. Also fair game

- **Accessibility regressions.** Run axe on every screen (the e2e only checks Home). Champagne gold
  on graphite: verify AA contrast for real (the author claims ratios in ADR-019 — check muted text
  `#8f8a7c`/`#6f6a5d` on tile/surface, amber on amber-surface, and the gold focus ring's visibility
  on every interactive element). Keyboard-only: can you reach and operate every control? Is the
  segmented control a real radiogroup?
- **Provider/secret backend** (PR #7, if not already reviewed): `LocalSecretStore` file perms
  (0600) and env-over-file precedence; the secrets API never returns a value; the OpenAI/Ollama
  streaming parsers' behavior on a hostile/truncated stream; cost/usage math.
- **Responsive/overflow:** the spec targets 5K but the app must survive a laptop and an iPhone.
  Find horizontal-scroll/overflow, an unreachable control behind the rail, or text clipped to
  invisibility at 1280px and 390px.

---

## 5. Rules of engagement

- **Prove it.** A failing Playwright/vitest test under `apps/web`, a pytest under
  `services/control-plane/tests/`, an exact repro (route + clicks + observed wrong behavior), or a
  traced call chain with `file:line`. Label **CONFIRMED** (reproduced/traced) vs **SUSPECTED**.
- **Attack at runtime.** Boot demo mode; click through every screen; drive the band handoff; enter
  Deep Work and try to reach an approval; paste a secret and inspect the DOM/network for leakage;
  keyboard-only a full approve/deny; axe every route; shrink to 390px.
- **Don't fix — report.** One- or two-sentence suggested fix per finding.
- **Severity:** `Critical` (a safety affordance lost or bypassable from the UI — e.g. an R4 phrase
  gate skippable, a secret value rendered/logged, an external write reachable without its approval;
  or the app is unusable/blank on a supported viewport) · `High` (a real control dropped or dead; a
  data path broken; a fabricated value shown as real; a hydration crash) · `Medium` (a11y/contrast
  failure, honesty-copy loss, overflow, a polling/perf storm) · `Low` (doc/behavior mismatch,
  minor aria gap).

---

## 6. How to give the feedback back to me

Produce **one Markdown report**:
- **Preferred:** write it to `docs/reviews/codex-findings-r4.md`, commit on branch
  `codex/adversarial-review-r4`, push, open a PR against `claude/build-brief-implementation-dbre2i`,
  and put any demonstrating tests in that branch under `apps/web/e2e/` or `apps/web/src` (vitest) /
  `services/control-plane/tests/`.
- **If you can't push:** paste the full report as your final message.

Use exactly this structure:

```
# Codex adversarial review R4 — AgenticOS Cockpit / OttoOS

## Summary
- Reviewed commit: <sha>
- One-line verdict.
- Counts: Critical N · High N · Medium N · Low N.
- What I ran (setup / gates / live attacks) and the environment.

## Findings (ranked, most severe first)
### F1. <title> — <Critical|High|Medium|Low> — <CONFIRMED|SUSPECTED>
- Which control / invariant / new seam it breaks.
- Location: <file:line>, <file:line>
- Failure scenario: <concrete route + interaction → observed wrong behavior>
- Reproduction: <exact clicks / test name> or traced call chain
- Impact: <what the user loses or an attacker gets>
- Suggested fix: <1–2 sentences>
- Evidence: <test path / screenshot / DOM or network excerpt>

## Things I tried hard to break but couldn't
- REQUIRED. For "nothing removed" (name the screens you diffed), the write-only secret path, the
  band autosubmit-once guard, the R4 phrase gate (rail + keyboard), and Deep Work approval
  reachability: how you attacked each and why it held. This tells me what's actually validated.

## New design concerns (not bugs)
- With a recommendation.

## Tests added
- Paths + one line each; pass/fail against the branch.
```

**Ranking:** severity, then confidence. Every CONFIRMED finding needs a runnable reproduction.
State explicitly if a severity band is empty rather than padding.

Start with **§2 (diff the 13 screens for a dropped/dead control or lost honesty line)** and
**§3's secret-leak + R4-phrase-gate checks** — a parallel reskin under a "nothing removed" rule is
most likely to have quietly dropped exactly one important thing, and the highest-severity UI bug
would be a safety gate that the new shell lets you skip.
