# PROGRESS.md — build log

Status legend: ✅ done · 🟡 in progress · ⬜ not started · ❌ blocked

## Current state

**Milestone 0 in progress.** Environment inspected; governing docs being written.

| Milestone | Status |
| --- | --- |
| M0 — Foundation & design contract | 🟡 |
| M1 — Durable local core | ⬜ |
| M2 — Claude runtime & live command control | ⬜ |
| M3 — Useful local skills | ⬜ |
| M4 — Integrations & automations | ⬜ |
| M5 — Hardening & polish | ⬜ |

## Environment (inspected 2026-07-12)

- Linux 6.18.5 container, repo `tkfriedrich-beep/Claude`, branch
  `claude/build-brief-implementation-dbre2i`
- Node v22.22.2, pnpm 10.33.0, Python 3.12.3, uv 0.8.17, GNU Make 4.3
- `claude` CLI present at `/opt/node22/bin/claude` (Agent SDK can spawn it)
- Playwright Chromium preinstalled at `/opt/pw-browsers` (do not run `playwright install`)
- Pre-existing unrelated repo content preserved: `copy_photos.sh`, `find_largest_files.sh`,
  `iran-news-timeline/`, `.claude/skills/voluntary-mind-essay/`

## Milestone log

### M0 — Foundation & design contract — 🟡

- [x] Environment inspection
- [x] BUILD_BRIEF.md committed into repo
- [ ] README, CLAUDE.md, docs/ (product, UX, architecture, contracts, threat model, roadmap, runbook)
- [ ] DECISIONS.md + PROGRESS.md
- [ ] Monorepo scaffold (Makefile, pnpm workspace, uv project)
- [ ] Design tokens + static cockpit shell

*Test gate:* repo installs cleanly (`make setup`), lint configs run.

### M1 — Durable local core — ⬜
### M2 — Claude runtime & live command control — ⬜
### M3 — Useful local skills — ⬜
### M4 — Integrations & automations — ⬜
### M5 — Hardening & polish — ⬜
