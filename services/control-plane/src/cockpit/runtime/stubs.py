"""Provider stubs — interfaces proven, deliberately unimplemented in the MVP (BUILD_BRIEF).

They register in the provider catalog so the UI can show them as "planned", and they raise
ProviderUnavailable if selected. Full implementations arrive per docs/ROADMAP.md.
"""

from __future__ import annotations

STUB_PROVIDERS: dict[str, str] = {
    "openai": "OpenAI runtime (planned) — same AgentRuntime contract, not yet implemented.",
    "ollama": "Ollama/Qwen local specialists (planned) — for private, offline routing.",
    "langgraph": "LangGraph/OpenClaw workflows (planned) — for complex graph workflows.",
}
