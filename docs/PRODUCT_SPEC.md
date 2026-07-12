# PRODUCT_SPEC.md

## What this is

AgenticOS Cockpit is an owned, local-first control plane for one person's life and work, with a
configurable assistant persona (**Otto**). It is not a chatbot skin and not a terminal wrapper:
it is a durable system of record for commands, runs, approvals, artifacts, memories, and
integrations, with Claude as the first pluggable reasoning runtime.

Within five seconds of opening, the user can answer: what matters now · what should I do next ·
what is Otto doing · what needs my approval.

## Product principles (binding)

1. Calm command center — motion communicates state, never decoration over readability.
2. Progressive disclosure — consumer-simple by default; logs/JSON/diagnostics behind expanders.
3. Human authority is visible — status, preview, risk, approval path, audit trail everywhere.
4. Local-first & portable — runs on a 16 GB MacBook without Docker/Redis/Postgres/Qdrant/Ollama.
5. Claude reasons; deterministic code governs.
6. One conductor, narrow specialists — triage → one skill → verification → quality review.
7. Structured state over magical memory — explicit, editable, attributable, exportable.
8. Mock-first, dry-run-first, approval-gated.
9. No false success — nothing shows as done without a confirming tool result.
10. No hidden-reasoning theater — concise plans/evidence, never private chain-of-thought.

## Core concepts

| Concept | Definition | Where |
| --- | --- | --- |
| Command | A user request or scheduled trigger | `POST /api/v1/commands`, schedules |
| Skill | Versioned workflow for a known outcome | `skills/*`, `skills` table |
| Agent | Reasoning runtime coordinating a bounded task | `cockpit/runtime/` |
| Tool | One atomic schema-defined capability | tool manifests in gateway |
| Connector | Adapter exposing tools/data of one external system | `connectors/*` + impl |
| Policy | Deterministic permission/risk/budget/autonomy rules | `policies` table + `policy.py` |
| Approval | Human decision before a proposed side effect | `approvals` table |
| Run | One auditable execution | `runs` + `run_events` |
| Artifact | Durable output (memo, report, diff, JSON) | `artifacts` + files |
| Memory | Structured, source-attributed, user-controlled record | `memories` (+ review queue) |
| Context pack | Named bounded set of sources + instructions for a run | `context_packs` |

MCP is a transport, not the domain model — MCP tools normalize into the same manifest as
everything else.

## Domains

Enabled by default: **Today, Work, Ventures, People, Knowledge, Personal**.
Scaffolded, disabled by default, read-only until explicitly enabled: **Health, Money, Home,
Travel** (high-sensitivity: separate, off, read-only first).
A domain controls available sources, skills, memory, and action policies.

## Graduated autonomy

Per skill and per connector: `0 off · 1 observe · 2 recommend · 3 draft · 4 act_with_approval ·
5 act_allowlist`. New integrations default to observe/draft. Scheduled skills support **Shadow
Mode** (run, show what would have happened, collect feedback). Autonomy is never promoted
automatically.

## Initial skills

| Skill | MVP depth | Notes |
| --- | --- | --- |
| Project Pulse | **Full** | local vault/projects scan → movement, risks, blocked, next actions, source links |
| Decision Memo | **Full** | Judgment-OS structure; Markdown + JSON artifacts; LLM-assisted when provider healthy |
| Business Idea Triage | **Full** | reads configured `bizideas` folder; scorecards; write-back only with approval |
| Morning Brief | Demo-labeled | agenda/commitments/projects/changes; calendar data is demo until Google connected |
| Daily Plan | Demo-labeled | priority sequence + time blocks; calendar changes stay drafts |
| Weekly Review | Functional | wins/commitments/slippage/decisions/lessons from local records |
| Commitment Sweep | Functional | finds promises in notes → proposes commitments via Memory Review |
| Research Run | Gated | requires a healthy provider; clearly reports its evidence limits |

## Connectors

MVP-implemented: **Local Files** (bounded roots, writes need approval), **Obsidian**
(vault-aware: /raw /wiki /projects), **n8n** (signed webhook, schema-bound, dry-run aware),
**MCP registry** (configure trusted servers, normalize tools, local policy applies).
Mocked/scaffolded with honest "not configured" cards: Google Workspace, Notion, GitHub.

## MVP acceptance criteria

The 18 criteria in `BUILD_BRIEF.md` §"MVP acceptance criteria" are the contract; PROGRESS.md
tracks each with evidence. Highlights: demo mode without credentials; approval-gated side
effects; Safe Mode blocks external writes; run history survives restart; `make doctor`/`make
test` honest; polished responsive home screen; Otto pulse reflects real run states and respects
reduced motion.

## Non-goals for the MVP

Hosted/multi-user deployment, production Google/Notion/GitHub OAuth, semantic vector retrieval,
voice, native wrappers, model routing, team RBAC — extension points preserved, nothing
prebuilt. See `docs/ROADMAP.md`.
