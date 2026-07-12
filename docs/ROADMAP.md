# ROADMAP.md

## MVP milestones (this build)

| Milestone | Contents | Test gate |
| --- | --- | --- |
| M0 Foundation | env inspection, docs/ADRs, design tokens, monorepo scaffold, static cockpit shell | `make setup` clean; lint configured |
| M1 Durable core | FastAPI, SQLite/Alembic, run FSM, event store+SSE, skill/connector registries, policy engine, approvals, mock provider/connectors, worker | pytest: FSM, policy, gateway, API; invalid transitions rejected |
| M2 Claude runtime | Agent SDK adapter, start/resume/interrupt/cancel, normalized events, approval bridge, usage capture, cwd restrictions | adapter unit tests (SDK mocked); mock-runtime session e2e path |
| M3 Local skills | Local Files + Obsidian connectors; Project Pulse, Decision Memo, Business Idea Triage; demo-labeled Morning Brief/Daily Plan; real-data briefing | skill fixtures pass; artifacts produced; sources linked |
| M4 Integrations & automations | n8n signed webhooks, MCP registry, Shadow-Mode schedules, health UI, mocked Google/Notion/GitHub | connector contract tests; shadow run produces preview only |
| M5 Hardening & polish | threat-model fixes, a11y, keyboard, reduced motion, empty/error/loading, e2e, screenshots, backup/export, docs | `make test` + `make e2e` pass; axe checks; desktop+mobile screenshots |

## Post-MVP (extension points preserved, not built)

Near: Google Workspace production OAuth (granular scopes), Notion + GitHub production
connectors, Firecrawl-backed Research Run, "What changed?" digests, memory review UX
refinements, richer usage analytics + OpenTelemetry adapter.

Mid: Qdrant/LightRAG behind `RetrievalProvider`; Ollama/Qwen private specialists +
privacy/complexity/cost model routing; LangGraph/OpenClaw complex workflows; visual skill
composer (generates manifest + tests + approval policy); context packs for roles (Consultant,
Operating Partner, Founder, Personal); voice via pluggable push-to-talk providers.

Far: Tauri desktop wrapper (OS keychain SecretStore, notifications, global shortcut, deep
links); mobile companion (capture + approvals); people/meeting intelligence; read-only finance
& health in isolated high-sensitivity domains; travel/home/location routines; team workspaces
(Postgres, background workers, RBAC, object storage, hosted deploy) — schema already carries
`workspace_id`.

Rule: nothing above may violate the architecture invariants in BUILD_BRIEF.md; provider and
storage swaps must remain module-local.
