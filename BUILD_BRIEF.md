# Claude Code Master Build Prompt — AgenticOS Cockpit

You are acting as the principal product architect, staff systems engineer, security engineer, prompt engineer, and senior UI/UX designer for this project.

## Mission

Build a local-first, consumer-simple, professional-grade AI command center called **AgenticOS Cockpit**. The configurable primary assistant persona is **Otto**. It should feel as responsive and engaging as a restrained, modern interpretation of Jarvis, while remaining calm, credible, accessible, and useful rather than theatrical.

This is not a generic chatbot and not merely a graphical wrapper around a terminal. It is an owned control plane for my life and work. Claude is the initial reasoning and agent runtime, but the product's state, policies, skills, approvals, integrations, audit history, and user experience must remain provider-independent so that OpenAI, Ollama/Qwen, LangGraph/OpenClaw, and future runtimes can be added later.

Use the supplied cockpit image as visual inspiration for information hierarchy, warm neutral styling, strong typography, cards, one-click skills, and a live activity rail. Do not clone it. Improve it with a purposeful animated system pulse, richer interaction states, progressive disclosure, polished empty/loading/error states, and a clearer human-control model. If the image is not available in the repository, proceed from this written brief.

The product must answer four questions within five seconds of opening:

1. What matters now?
2. What should I do next?
3. What is Otto/Claude doing?
4. What needs my approval?

## Product principles

1. **Calm command center, not sci-fi clutter.** Motion must communicate system state. Never sacrifice readability for visual effects.
2. **Progressive disclosure.** The default experience is consumer-friendly. Technical logs, raw JSON, prompts, token details, and connector diagnostics sit behind expandable views.
3. **Human authority is visible.** Every consequential action has a clear status, preview, risk level, approval path, and audit trail.
4. **Local-first and portable.** The MVP must run comfortably on a 14-inch Apple Silicon Mac with 16 GB RAM. Do not require Docker, Redis, Postgres, Qdrant, or Ollama to use the core product.
5. **Claude reasons; deterministic code governs.** Do not put security rules, permissions, routing, retries, or side-effect control only in prompts.
6. **One conductor, narrow specialists.** Avoid an uncontrolled multi-agent swarm. Use the routing pattern: Clarification and Triage -> one specialized skill -> Verification -> Quality Review.
7. **Structured state over magical memory.** Important facts, preferences, commitments, projects, sources, and decisions must be explicit, editable, attributable, and exportable.
8. **Mock-first, dry-run-first, approval-gated.** The app must be useful without credentials and safe before it is autonomous.
9. **No false success.** Never show an action as completed unless a tool result or connector response confirms it.
10. **No hidden-reasoning theater.** Show concise plans, action summaries, tool events, evidence, and decision rationale. Do not expose or claim to expose private chain-of-thought.

## How you must work

Before implementation:

1. Inspect the current repository, operating system, installed runtimes, package managers, and any existing files. Preserve useful work.
2. Create or update these files before large-scale coding:
   - `README.md`
   - `CLAUDE.md`
   - `docs/PRODUCT_SPEC.md`
   - `docs/UX_SPEC.md`
   - `docs/ARCHITECTURE.md`
   - `docs/INTEGRATION_CONTRACTS.md`
   - `docs/THREAT_MODEL.md`
   - `docs/ROADMAP.md`
   - `docs/RUNBOOK.md`
   - `DECISIONS.md`
   - `PROGRESS.md`
3. Write a concise implementation plan with milestones, risks, and test gates. Then continue building; do not stop after planning unless a genuinely blocking decision exists.
4. Ask only blocking questions. Make sensible, reversible defaults for routine choices and document them in `DECISIONS.md`.
5. Work milestone by milestone. At the end of each milestone, run relevant formatting, linting, type checks, unit tests, integration tests, and UI smoke tests. Record actual results in `PROGRESS.md`.
6. Do not claim completion based on code inspection alone. Launch the app, exercise the critical paths, and capture screenshots for desktop and mobile verification.
7. Use current stable package versions and confirm APIs against official documentation. Do not invent package methods or rely on deprecated examples.
8. Never store real credentials in source control, fixtures, screenshots, or logs. Provide `.env.example` and a mock/demo mode.
9. Do not modify files outside the repository without explicit approval.
10. Do not push to a remote repository or deploy anything unless explicitly instructed.

## Recommended technical architecture

Use a small monorepo with a web application and a durable local control-plane service.

### Front end

- Next.js with TypeScript and the App Router
- Tailwind CSS
- shadcn/ui primitives, customized into a coherent design system rather than left looking like stock components
- Accessible SVG/CSS motion for the Otto pulse; avoid heavy WebGL in the MVP
- TanStack Query or an equivalent typed data-fetching layer
- Server-Sent Events for agent/run event streaming
- WebSocket reserved for later voice/audio or truly bidirectional realtime needs
- PWA-ready architecture; do not build a native wrapper in the first milestone

### Control plane

- Python 3.12+ with FastAPI
- Pydantic models and typed async code
- Official Claude Agent SDK through a dedicated provider adapter
- SQLAlchemy 2.x and Alembic
- SQLite in WAL mode for the local MVP
- SQLite FTS5 for initial text retrieval
- A persistent jobs table and lightweight in-process worker loop; no mandatory Redis
- Structured JSON logging with redaction
- OpenAPI as the source of truth for web/control-plane contracts; generate or validate the TypeScript client from it

### Tooling

- `pnpm` for the web workspace
- `uv` preferred for Python dependency and environment management, with documented fallback commands if unavailable
- Vitest for TypeScript unit tests
- Pytest for Python unit/integration tests
- Playwright for end-to-end tests and screenshots
- Accessibility checks using an automated axe-compatible test plus manual keyboard verification
- A root `Makefile` or equivalent scripts so the main commands are simple:
  - `make setup`
  - `make dev`
  - `make test`
  - `make doctor`
  - `make demo`

### Repository shape

Use a structure close to this, adapting only when justified:

    apps/
      web/
    services/
      control-plane/
    packages/
      ui/
      contracts/
    skills/
      morning-brief/
      daily-plan/
      project-pulse/
      decision-memo/
      research-run/
      weekly-review/
      commitment-sweep/
      business-idea-triage/
    connectors/
      local-files/
      obsidian/
      n8n/
      mcp/
      notion/
      google-workspace/
      github/
    data/
      demo/
    docs/
    scripts/
    .claude/
      skills/

Keep build-time Claude Code skills under `.claude/skills/`. Keep runtime product skills under `skills/`. Do not conflate the two.

## Architecture invariants

These are non-negotiable unless you document a compelling reason in `DECISIONS.md`:

1. The UI must never import Anthropic, OpenAI, Ollama, LangGraph, or connector SDKs directly.
2. No runtime skill may call a third-party API directly. It must invoke a typed tool through the Tool Gateway.
3. No third-party connector may decide whether an action is allowed. The Policy and Approval Gateway owns that decision.
4. No model provider may own canonical user data, memory, run history, or permissions.
5. Prompts are versioned assets. Policies are deterministic code. Tool inputs and outputs are schema-validated.
6. Every external mutation receives an idempotency key where supported and records its confirmation result.
7. Every run is reconstructable from stored events without storing secrets or unrestricted raw sensitive payloads.
8. All provider-specific events are normalized before reaching the UI.
9. All integrations implement a common connector contract and health check.
10. All future hosted/multi-user needs are anticipated with `workspace_id`, but the MVP remains single-user and local-first.

Use this conceptual data flow:

    User
      -> Cockpit UI
      -> Command API
      -> Intent/Triage Router
      -> One Skill
      -> Plan
      -> Policy + Approval Gateway
      -> Agent Runtime
      -> Typed Tool Gateway
      -> Connector/MCP/n8n/local script
      -> Tool Result
      -> Verification
      -> Quality Review
      -> Human-readable result + artifacts + audit events

## Core concepts and boundaries

Define these explicitly in code and documentation:

- **Command:** A user request or scheduled trigger.
- **Skill:** A versioned workflow for accomplishing a known outcome.
- **Agent:** A reasoning runtime that plans and coordinates within a bounded task.
- **Tool:** One atomic, schema-defined capability.
- **Connector:** An adapter that exposes tools and data from one external system.
- **Policy:** Deterministic rules governing permissions, risk, budgets, and autonomy.
- **Approval:** A human decision required before a proposed side effect.
- **Run:** One auditable execution of a command or skill.
- **Artifact:** A durable output such as a memo, report, draft, diff, or JSON result.
- **Memory:** A structured, source-attributed record that the user can inspect, edit, export, or delete.
- **Context pack:** A named, bounded set of data sources and instructions used for a run.

MCP is an integration transport, not the product's domain model. Normalize MCP tools into the same internal tool manifest used by direct API, CLI, local-file, and n8n connectors.

## Model and agent runtime abstraction

Create a provider-neutral `AgentRuntime` interface with capabilities comparable to:

- `start_session()`
- `resume_session()`
- `send_input()`
- `interrupt()`
- `stream_events()`
- `request_approval()`
- `approve()`
- `deny()`
- `cancel()`
- `get_usage()`
- `close_session()`

Implement `ClaudeAgentRuntime` first using the current official Claude Agent SDK. Do not build the core around scraping terminal output. A CLI adapter may exist only as a clearly labeled development fallback.

Normalize provider events into a stable internal event model, including:

- `run.queued`
- `run.started`
- `agent.status_changed`
- `assistant.message_delta`
- `plan.created`
- `tool.proposed`
- `approval.required`
- `approval.resolved`
- `tool.started`
- `tool.progress`
- `tool.completed`
- `tool.failed`
- `artifact.created`
- `verification.completed`
- `run.completed`
- `run.failed`
- `run.cancelled`

Support long-lived interactive sessions, interruption, resume, permission requests, and streaming updates. Persist the external provider session ID separately from the internal run/session ID.

The default assistant system prompt should be a purpose-built Otto prompt, not a coding-assistant persona. Otto is calm, direct, skeptical of unsupported claims, source-aware, concise by default, and proactive within policy. Otto distinguishes facts, inferences, and recommendations; exposes uncertainty; and never claims an external action succeeded without evidence.

Use subagents only for narrow isolation when a side task would flood the main context, such as research, large log analysis, or verification. Do not use multiple agents merely to make the architecture sound sophisticated.

Add provider stubs/interfaces for:

- OpenAI
- Ollama/Qwen local specialists
- LangGraph/OpenClaw workflows

Do not fully implement those providers in the MVP.

## Agentic loop

Implement a visible, testable loop:

1. **Capture intent** — parse the request and selected context pack.
2. **Clarify or classify** — ask only when ambiguity changes consequences; otherwise choose a reversible assumption and display it.
3. **Route** — select exactly one primary skill or generic bounded assistant mode.
4. **Retrieve context** — use only allowed sources for the selected domain and skill.
5. **Plan** — create a concise structured plan with expected tools, side effects, cost/step budget, and success checks.
6. **Policy check** — deterministic risk and permission evaluation.
7. **Approval** — pause for human approval when required.
8. **Execute** — invoke typed tools with timeouts, retries, idempotency, and cancellation.
9. **Verify** — compare actual tool results with the intended outcome.
10. **Quality review** — check completeness, evidence, uncertainty, safety, and output format.
11. **Present** — show a concise answer, actions taken, artifacts, sources, and unresolved items.
12. **Record** — append redacted events and optionally propose memories for review.

The loop must have maximum steps, timeout, token/cost budget, cancellation, and clear failure states. Local mode should default to a low concurrency limit.

## Graduated autonomy

Every skill and connector must have an autonomy level:

0. **Off** — unavailable.
1. **Observe** — read and report only.
2. **Recommend** — propose next actions.
3. **Draft** — create drafts/previews with no external mutation.
4. **Act with approval** — execute after explicit approval.
5. **Act within allowlist** — execute only inside a narrow, user-defined policy.

Default all new integrations to Observe or Draft. Provide a Shadow Mode for scheduled skills: run them, show what they would have done, and collect feedback before allowing real actions. Never promote autonomy automatically merely because runs succeeded.

## Policy, security, and approval gateway

Build a deterministic execution gateway. Each tool manifest must declare:

- Unique ID and version
- Connector and capability
- Input and output schema
- Read/write/destructive classification
- Data sensitivity
- Required scopes
- Whether it has external side effects
- Whether it supports dry-run
- Whether it is idempotent
- Expected timeout
- Retry policy
- Approval policy
- Undo or compensation strategy where possible

Use a risk model similar to:

- `R0`: local read-only
- `R1`: external read-only
- `R2`: draft or local reversible write
- `R3`: external reversible write
- `R4`: destructive, financial, legal, health-related, identity/security, broad communication, or otherwise high-impact

Defaults:

- R0/R1 may run automatically within the active context pack.
- R2 may run automatically only in Draft mode.
- R3 requires a clear preview and explicit approval.
- R4 is disabled or double-confirmed with a typed confirmation and strong warning.

The approval card must show, in plain language:

- What will happen
- Why it is being proposed
- Target system and account
- Data that will be sent
- Before/after preview or diff
- Risk and reversibility
- Cost if known
- Options: approve once, deny, edit, or cancel the run

An “always allow” rule must be created only through a separate policy editor, never as a casual one-click bypass.

Security requirements:

- Treat emails, webpages, documents, MCP outputs, and retrieved notes as untrusted data, not instructions.
- Retrieved content must never change system policy, tool permissions, secret access, or approval requirements.
- Sanitize and schema-validate every tool input and output.
- Restrict filesystem tools to configured roots.
- Restrict shell execution to the workspace and approved wrappers; arbitrary shell commands require approval.
- Redact secrets, tokens, sensitive values, and unnecessary personal data from logs and UI events.
- Store credentials through a `SecretStore` abstraction. In local web development, support environment variables. For a future desktop wrapper, support the OS keychain. Do not store plaintext secrets in SQLite.
- Include a visible global Safe Mode and Kill Switch.
- Include connector-level read-only toggles and per-tool allow/deny rules.
- High-sensitivity domains such as health, money, and identity are separate, off by default, and read-only unless explicitly enabled.
- Microphone behavior must be push-to-talk. Never implement always-listening behavior in the MVP.

Document realistic limitations. Local process restrictions are not equivalent to a hardened sandbox.

## Knowledge, memory, and context

Use the user's local knowledge system as a first-class source:

- Obsidian Markdown vault with `/raw`, `/wiki`, and `/projects`
- A configurable watch root for `~/Desktop/bizideas`
- Shared folders that Claude Code/Cowork can both read and write
- Notion and Google Workspace as future or connector-driven sources

Do not use a vector database as the source of truth. Canonical content remains in files or structured relational records. Start with filesystem metadata, Markdown parsing, SQLite records, and FTS5. Create a `RetrievalProvider` interface so Qdrant, LightRAG, or another semantic index can be added later.

Define distinct memory types:

- Profile and preferences
- People and relationships
- Projects and goals
- Commitments and follow-ups
- Decisions and rationale
- Reusable procedures
- Temporary working context

Every durable memory must contain:

- Source reference
- Created and last-verified timestamps
- Confidence
- Sensitivity level
- Domain
- Optional expiry/TTL
- User-visible rationale for why it was saved

Do not silently store every conversation. Otto may propose a memory, but the user can approve, edit, reject, export, or delete it. Build a Memory Review queue.

## Initial domains

Support domain-aware context and permissions. Enable only the lower-risk core domains by default:

- Today
- Work
- Ventures
- People
- Knowledge
- Personal

Scaffold, but keep disabled by default:

- Health
- Money
- Home
- Travel

A domain controls available sources, skills, memory, and action policies.

## UX and visual direction

The product should feel like a premium personal operating system: warm, quiet, precise, and alive.

### Visual system

Use a warm cream/light theme inspired by the reference image and a refined dark “midnight” theme. Suggested starting tokens, adjustable during design review:

- Light background: warm parchment
- Light surface: near-white ivory
- Primary text: almost-black ink
- Muted text: warm gray
- Accent: restrained emerald/teal
- Warning: amber
- Danger: muted red
- Dark background: near-black green/graphite
- Dark surface: raised charcoal

Use strong sans-serif typography for headings and a restrained monospace only for event timestamps, IDs, and optional technical details. Use generous spacing, crisp borders, subtle elevation, and no excessive glassmorphism.

### The Otto pulse

Create an elegant SVG/CSS pulse/orb that represents state rather than decoration:

- Idle: slow breathing
- Listening: responsive waveform/ring
- Thinking: controlled orbit or layered pulse
- Acting: directional progress motion
- Waiting for approval: amber heartbeat
- Completed: brief resolved expansion
- Error: steady, non-alarming alert state

Respect `prefers-reduced-motion`. The app must remain fully usable with motion disabled.

### Desktop information architecture

Use a three-zone layout:

1. **Left navigation** — compact and stable
2. **Primary workspace** — briefing, commands, skills, agenda, and artifacts
3. **Right activity/inspector rail** — active run, approvals, system pulse, and human-readable event timeline

Suggested navigation:

- Home
- Command
- Agenda
- Projects
- People
- Knowledge
- Skills
- Automations
- Integrations
- Approvals
- History
- Settings

The right rail collapses on smaller screens. Raw logs are hidden behind “Technical details.”

### Mobile behavior

Mobile is primarily for:

- Capturing a thought or request
- Reading the briefing
- Approving/denying actions
- Checking active runs
- Reviewing the next agenda item

Do not squeeze the entire desktop administration interface onto mobile. Use bottom navigation and full-screen sheets for approvals and command capture.

### Home screen

Build a polished home screen containing:

- Personalized greeting and current date
- Otto pulse and universal command composer
- “What matters now” briefing
- Approval queue summary
- Active run with pause/cancel controls
- Suggested next actions
- One-click skill cards
- Today’s agenda
- Project pulse
- At-a-glance metrics that reflect real activity, not vanity numbers
- Connector/system health summary

Use `Cmd/Ctrl + K` for a universal command palette. Provide slash commands for power users without making them required.

### Command experience

The command composer supports:

- Natural language
- Skill selection
- Context pack selection
- Domain selection
- Optional attachments
- Read-only/Draft/Act mode
- Optional budget and deadline

Before executing a consequential task, show a concise plan. During execution, show human-readable events such as “Reading your project notes,” “Preparing a calendar change,” or “Waiting for approval,” not raw internal monologue.

## Core screens for the MVP

Implement these as real, navigable screens rather than static mockups:

1. **Onboarding**
   - User name and assistant name
   - Data location selection
   - Obsidian vault selection/path entry
   - `bizideas` folder selection/path entry
   - Claude provider setup using only supported official authentication
   - Safe Mode and default autonomy level
   - Demo data option

2. **Home**
   - Full cockpit described above

3. **Command**
   - Persistent conversation/run surface
   - Start, resume, interrupt, cancel
   - Plan and tool timeline
   - Artifacts panel
   - Source chips

4. **Skills**
   - Searchable skill library
   - Skill detail with purpose, required data, tools, risk, autonomy, schedule, and version
   - Run now and configure actions

5. **Approvals**
   - Pending, resolved, expired
   - Diff/preview
   - Clear risk labeling

6. **Automations**
   - Schedules
   - Shadow Mode
   - Last/next run
   - Pause
   - Failure handling

7. **Integrations**
   - Connector registry
   - Health, scopes, mode, last sync, available tools
   - Add MCP server configuration
   - Add n8n webhook
   - Local paths
   - Mock Notion, Google Workspace, and GitHub cards until genuinely configured

8. **History**
   - Runs, status, duration, tools, costs/tokens where available, artifacts, errors
   - Replayable human-readable event timeline

9. **Settings**
   - Appearance
   - Safe Mode
   - Budgets
   - Storage/export
   - Memory review
   - Domain permissions
   - Connector policies

## Initial skill system

Each skill lives in its own folder and includes:

- `manifest.yaml`
- `SKILL.md`
- Input JSON Schema
- Output JSON Schema
- Optional prompt templates
- Tool allowlist
- Policy requirements
- Verification checklist
- Example fixtures
- Unit/evaluation cases
- Version and changelog

A manifest should capture at least:

- `id`
- `name`
- `description`
- `version`
- `domains`
- `risk_level`
- `default_autonomy`
- `required_connectors`
- `allowed_tools`
- `input_schema`
- `output_schema`
- `supports_schedule`
- `supports_dry_run`
- `timeout_seconds`
- `max_steps`
- `verification_rules`

Build these initial skill definitions:

1. **Morning Brief** — summarize agenda, commitments, active projects, and notable changes with source links and freshness.
2. **Daily Plan** — propose a realistic priority sequence and time blocks; calendar changes remain drafts until approved.
3. **Project Pulse** — scan configured project Markdown/folders and report movement, risks, blocked items, and next actions.
4. **Decision Memo** — use a Judgment OS-style structure: decision, context, options, evidence, assumptions, trade-offs, recommendation, confidence, pre-mortem, and review date.
5. **Research Run** — produce a source-backed research memo with explicit facts, inferences, unknowns, and citations. External browsing is connector/provider dependent.
6. **Weekly Review** — wins, commitments, slippage, decisions, lessons, and next-week focus.
7. **Commitment Sweep** — find promises/follow-ups in structured records and notes, then propose next actions.
8. **Business Idea Triage** — inspect the configured `bizideas` folder, create a structured scorecard, and propose the next validation action.

For the first usable milestone, fully implement at least:

- Project Pulse using local files/Obsidian
- Decision Memo using structured inputs and artifact export
- Business Idea Triage using the configured local folder

Morning Brief and Daily Plan may use demo/mock connector data until Google Workspace is configured, but they must be clearly labeled as demo-derived.

## Connector architecture

Define a common connector interface, conceptually:

- `get_manifest()`
- `health_check()`
- `list_tools()`
- `execute(tool_id, validated_input, execution_context)`
- `normalize_result()`
- `redact_for_log()`

A connector manifest must include:

- ID, name, version, category
- Auth type
- Supported capabilities
- Required scopes
- Data sensitivity
- Available tools
- Read/write mode
- Health status
- Last successful use

Implement these first:

1. **Local Files connector** — bounded roots, Markdown/text/JSON, safe reads, explicit write approval.
2. **Obsidian connector** — local filesystem adapter aware of `/raw`, `/wiki`, and `/projects`.
3. **n8n connector** — signed webhook invocation with input/output schema, timeout, retry, dry-run where the workflow supports it, and clear external-action labeling.
4. **Generic MCP connector registry** — configure trusted servers, discover tools, normalize their schemas, and apply local policy before execution.

Scaffold, document, and mock-test:

- Google Workspace: Gmail, Calendar, Drive
- Notion
- GitHub

Prefer MCP when it is trusted and adequate, direct APIs when stronger auth/reliability/control is needed, n8n when it already owns a workflow, and narrow CLI wrappers for stable local operations. The user should not need to care which transport is used.

## Data model

Create migrations and repositories for at least:

- `workspaces`
- `user_profiles`
- `domains`
- `projects`
- `people`
- `commitments`
- `agent_profiles`
- `provider_sessions`
- `skills`
- `skill_versions`
- `connectors`
- `connector_tools`
- `policies`
- `schedules`
- `runs`
- `run_events`
- `tool_calls`
- `approvals`
- `artifacts`
- `memories`
- `memory_sources`
- `context_packs`

Do not create tables merely to appear comprehensive. Keep fields minimal but preserve IDs, versioning, source attribution, status, timestamps, and `workspace_id`.

Use explicit run states such as:

- `queued`
- `triaging`
- `planning`
- `awaiting_approval`
- `executing`
- `verifying`
- `reviewing`
- `completed`
- `failed`
- `cancelled`
- `interrupted`

Implement valid transitions as a finite-state machine or equivalent deterministic transition table and test invalid transitions.

## API surface

Design versioned endpoints under `/api/v1`, including:

- health and doctor status
- onboarding/configuration
- command submission
- session start/resume/interrupt/cancel
- run detail/history
- run event stream via SSE
- approvals list/resolve
- skills list/detail/run/configure
- connectors list/detail/health/configure
- automations list/create/pause/run-shadow
- artifacts list/download/export
- memory review/list/update/delete/export
- settings and policy management

Use typed problem responses for errors. Correlation IDs must flow from the browser through the control plane, tool gateway, and logs.

## Observability and cost control

For every run, capture when available:

- Model/provider
- Duration
- Step count
- Tool calls
- Tokens and cost estimate
- Cache/usage metadata
- Errors and retries
- Approval wait time
- Artifacts
- Final verification status

Provide daily and per-run budgets. Add an optional OpenTelemetry adapter, but do not require an external telemetry backend for local use. The UI should show a simple usage summary and allow technical export.

## Failure and recovery behavior

Build explicit handling for:

- Provider unavailable
- Authentication failure
- Connector unavailable
- Schema mismatch
- Timeout
- Rate limit
- User denial
- Partial completion
- Process restart during a run
- Stale approval
- Duplicate action
- Verification failure

On process restart, mark in-flight runs as interrupted, preserve events, and offer resume or restart where safe. Do not silently re-run external writes.

## MVP milestone plan

### Milestone 0 — Foundation and design contract

- Inspect environment
- Produce documentation and ADRs
- Create design tokens and component inventory
- Scaffold monorepo, scripts, demo mode, and CI-friendly tests
- Add a polished static cockpit shell with responsive layout

### Milestone 1 — Durable local core

- FastAPI control plane
- SQLite/Alembic
- Run state machine
- Event store and SSE
- Skill registry
- Connector registry
- Policy engine and approval records
- Mock provider and mock connectors

### Milestone 2 — Claude runtime and live command control

- Claude Agent SDK adapter
- Start/resume/interrupt/cancel
- Normalized event stream
- Permission/approval bridge
- Token/cost metadata where available
- Safe working-directory restrictions

### Milestone 3 — Useful local skills

- Local Files and Obsidian connectors
- Project Pulse
- Decision Memo with Markdown/JSON export
- Business Idea Triage
- Home briefing backed by real local data plus clearly labeled demo data for unavailable services

### Milestone 4 — Integrations and automations

- n8n webhook connector
- MCP registry
- Shadow Mode schedules
- Integration health UI
- Mocked/scaffolded Google Workspace, Notion, and GitHub connectors

### Milestone 5 — Hardening and polish

- Threat-model fixes
- Accessibility
- Keyboard navigation
- Reduced motion
- Error/empty/loading states
- E2E tests
- Desktop and mobile screenshots
- Backup/export
- Setup and troubleshooting documentation

Continue through the milestones required for a working MVP. If context or time becomes constrained, leave the repository in a runnable state, update `PROGRESS.md` precisely, and state the next command to continue. Never leave a broken half-migration without documenting recovery.

## MVP acceptance criteria

The MVP is complete only when all of the following are true:

1. A new user can run setup and launch the app with documented commands and no mandatory Docker services.
2. Demo mode works without external credentials.
3. The home screen is polished, responsive, keyboard accessible, and visually verified at desktop and mobile sizes.
4. The Otto pulse reflects real run states and respects reduced motion.
5. A user can start a Claude-backed session, see streamed events, interrupt it, resume it where supported, and cancel it.
6. A proposed side effect creates an approval request and cannot execute before approval.
7. Safe Mode prevents external writes.
8. Project Pulse can read configured local Markdown/project data and produce a source-linked result.
9. Decision Memo produces a durable Markdown artifact and structured JSON result.
10. Business Idea Triage can process the configured ideas folder without altering source files unless approved.
11. Run history survives restarts and displays a human-readable timeline.
12. Connector health and permissions are visible.
13. Sensitive data and secrets do not appear in normal logs.
14. Unit tests cover policy decisions, state transitions, schemas, and skill routing.
15. E2E tests cover onboarding/demo, running a skill, approval denial, approval success in a mock connector, run history, and responsive navigation.
16. `make doctor` reports missing prerequisites and configuration clearly.
17. `make test` passes, or any remaining failures are explicitly documented with evidence and are not hidden.
18. The README contains setup, architecture summary, security model, data locations, backup/export, and troubleshooting.

## Future roadmap to preserve in the architecture, not build now

Keep clean extension points for:

- Google Workspace production OAuth and granular scopes
- Notion production integration
- GitHub operations
- Firecrawl-backed research
- Qdrant or LightRAG semantic retrieval
- Ollama/Qwen private specialist routing
- LangGraph/OpenClaw complex workflows
- Voice input and TTS through pluggable providers
- Tauri desktop wrapper for OS keychain, notifications, global shortcut, and deep links
- Mobile companion focused on capture and approvals
- Relationship/people intelligence and meeting preparation
- Read-only finance and health summaries in isolated high-sensitivity domains
- Travel mode, home automation, and location-aware routines
- “What changed?” digests across projects and sources
- A visual skill composer that generates a manifest, tests, and approval policy
- Context packs for roles such as Consultant, Operating Partner, Founder, and Personal
- Team workspaces, Postgres, background workers, RBAC, object storage, and hosted deployment
- Model routing based on privacy, complexity, latency, and cost

Do not prebuild infrastructure for all of this. Preserve interfaces and schemas, then ship the local cockpit.

## Quality bar

The experience should look intentional enough to show a client or future teammate. Avoid lorem ipsum, fake analytics, placeholder charts without meaning, and generic AI marketing copy. Use realistic demo data clearly labeled as demo. Every screen needs loading, empty, error, success, and permission-denied states.

Code must be typed, modular, readable, and documented where the reasoning is not obvious. Prefer boring, dependable infrastructure over fashionable complexity. Keep boundaries strong enough that another engineer can replace Claude, SQLite, the UI, or an individual connector without rewriting the product.

## Begin now

1. Inspect the repository and environment.
2. Restate the proposed architecture in no more than 15 lines, including any deviations from this brief.
3. Create the documentation and milestone plan.
4. Scaffold the project.
5. Implement and verify the working MVP rather than stopping at mockups.
6. At completion, report:
   - What is working
   - What is mocked or scaffolded
   - Test results
   - Security limitations
   - Exact commands to run
   - The next three highest-value improvements
