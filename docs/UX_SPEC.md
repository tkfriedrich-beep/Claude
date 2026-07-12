# UX_SPEC.md

Feel: a premium personal operating system — warm, quiet, precise, alive. Inspired by the
reference cockpit image (information hierarchy, warm neutrals, strong typography, cards,
one-click skills, live activity rail) but improved: purposeful system pulse, richer interaction
states, progressive disclosure, polished empty/loading/error states, explicit human-control
model. Never sci-fi clutter.

## Design tokens (source of truth: `apps/web/src/app/globals.css`)

Light "parchment":
- `--background` warm parchment `#f4f1ea` · `--surface` ivory `#fbfaf7` · `--surface-raised` `#ffffff`
- `--ink` almost-black `#1c1e1b` · `--muted` warm gray `#6f6b60` · `--line` `#e3ded2`
- `--accent` restrained emerald `#12695b` (hover `#0d5044`) · `--accent-soft` `#e3efe9`
- `--warn` amber `#b97c10` / soft `#f6ecd7` · `--danger` muted red `#a8452f` / soft `#f3e2dc`

Dark "midnight":
- `--background` near-black green/graphite `#131715` · `--surface` `#1a201d` · raised `#222925`
- `--ink` `#eceae2` · `--muted` `#9a978c` · `--line` `#2d342f`
- `--accent` `#4fb39b` · warn `#d9a03c` · danger `#c96f57`

Typography: Inter (variable) for UI/headings — strong weights (600/650) for headings, 400/450
body. Monospace (`ui-monospace` stack) **only** for timestamps, IDs, and technical details.
Radii: cards 14px, controls 10px, chips 999px. Borders 1px solid `--line`; subtle elevation
(`shadow-sm`-scale); no glassmorphism. Spacing on a 4px grid, generous (cards p-5/p-6).

Both themes ship; toggle via `data-theme` on `<html>`; respects `prefers-color-scheme` default.

## The Otto pulse

An SVG/CSS orb encoding real system state (never decoration):

| State | Motion | Color note |
| --- | --- | --- |
| idle | slow 6s breathing scale/opacity | accent, low amplitude |
| listening | responsive ring ripple | accent |
| thinking | layered counter-rotating orbit arcs | accent |
| acting | directional sweep progress | accent, brisker |
| waiting_approval | amber heartbeat (double-thump) | warn |
| completed | one brief resolve expansion, then idle | accent |
| error | steady soft alert ring, no flashing | danger, calm |

Driven by active run status from the event stream. Under `prefers-reduced-motion`, all
animation stops; state is shown by color + a text label (the app is fully usable motion-free).

## Layout

**Desktop (≥1024px):** three zones — left nav (compact, stable, collapsible to icons),
primary workspace, right activity/inspector rail (active run, approvals, pulse, human-readable
timeline). Rail collapses below 1280px into a toggleable drawer.

Left nav: Home, Command, Agenda, Projects, People, Knowledge, Skills, Automations,
Integrations, Approvals (with pending badge), History, Settings.

**Mobile (<768px):** bottom tab bar — Home, Command, Approvals, Agenda, More. Mobile is for
capture, reading the briefing, approving/denying, checking runs, next agenda item. Approvals
and command capture open as full-screen sheets. No desktop admin cramming.

## Home screen (the cockpit)

Order top-to-bottom: greeting + date + Safe-Mode/kill-switch status · Otto pulse + universal
composer · "What matters now" briefing · approval queue summary (amber when pending) · active
run card with pause/cancel · suggested next actions · one-click skill cards · today's agenda
(demo-labeled when demo) · project pulse · at-a-glance metrics (real counts only: runs today,
approvals pending, artifacts this week, connector health) · connector/system health strip.

`Cmd/Ctrl+K` opens the command palette (navigate, run skill, toggle safe mode). Slash commands
in the composer (`/skill`, `/mode draft`) for power users — never required.

## Command experience

Composer supports natural language; skill, context-pack, domain selectors; attachments
(path references); mode selector **Read-only / Draft / Act**; optional budget + deadline.
Consequential tasks show a concise plan first. During execution the timeline shows
human-readable events ("Reading your project notes…", "Waiting for your approval…"), with raw
JSON behind "Technical details". Controls: interrupt, resume, cancel. Artifacts panel and
source chips on the right.

## Approval card (exact contents)

What will happen · why proposed · target system/account · data to be sent · before/after or
diff preview · risk level + reversibility · cost if known · buttons **Approve once** / **Deny**
/ **Edit** / **Cancel run**. "Always allow" lives only in the Settings policy editor, never on
the card. R4 additionally requires typing a confirmation phrase (disabled by default).

## States, accessibility, quality bar

Every screen implements loading (skeletons), empty (helpful, action-forward), error (retry +
detail expander), success, and permission-denied states. No lorem ipsum, no fake analytics;
demo data is realistic and labeled `demo`. Keyboard: full tab order, visible focus rings
(`--accent` 2px), Esc closes layers, Cmd+K palette, `a` approve / `d` deny on focused approval
card. Targets ≥44px on mobile. Contrast AA-verified for both themes. Screen-reader labels on
pulse state changes via `aria-live="polite"` status text.
