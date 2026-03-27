# Claude Cowork Schema

A multi-layer agent orchestration schema for Claude Code, adapted from the
OpenClaw architecture. Uses Claude Code's native primitives — workspaces,
subagents, skills, hooks, and MCP servers — to implement a structured
delegation and execution system.

## Architecture Layers

| Layer | OpenClaw | Claude Cowork |
|-------|----------|---------------|
| 2 | Otto (Chief of Staff) | **Coordinator** — main CLAUDE.md router |
| 3 | KinvoyPrez + Specialists | **Specialists** — workspace-isolated agents |
| 4 | Execution (tools/APIs) | **Execution** — MCP servers, skills, subagents |
| 5 | State (Notion/Drive/GitHub) | **State** — structured memory files + GitHub |

## Quick Start

1. Copy `workspaces/` into your project root
2. Copy `CLAUDE.md` to your project root (or merge with existing)
3. Configure MCP servers in `settings.json` as needed
4. Run `claude` — the Coordinator routes your requests

## Directory Structure

```
cowork-schema/
├── CLAUDE.md                    # Layer 2: Coordinator instructions
├── workspaces/
│   ├── specialist-sales/        # Layer 3: Sales specialist
│   │   └── CLAUDE.md
│   ├── specialist-marketing/    # Layer 3: Marketing specialist
│   │   └── CLAUDE.md
│   ├── specialist-finance/      # Layer 3: Finance specialist
│   │   └── CLAUDE.md
│   ├── specialist-operations/   # Layer 3: Operations specialist
│   │   └── CLAUDE.md
│   └── specialist-research/     # Layer 3: Research specialist
│       └── CLAUDE.md
├── skills/                      # Layer 4: Reusable playbooks
│   ├── github-ops.md
│   ├── deep-research.md
│   └── seo-tools.md
├── state/                       # Layer 5: Structured memory
│   ├── SOUL.md
│   ├── USER.md
│   └── MEMORY.md
└── settings.json                # MCP servers & permissions
```
