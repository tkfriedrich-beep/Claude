"""Provider-neutral agent runtimes."""

from collections.abc import Callable

from cockpit.runtime.base import AgentRuntime, ProviderUnavailable, RuntimeEvent, TurnResult
from cockpit.runtime.claude import ClaudeAgentRuntime
from cockpit.runtime.mock import MockAgentRuntime
from cockpit.runtime.ollama_runtime import OllamaAgentRuntime
from cockpit.runtime.openai_runtime import OpenAIAgentRuntime
from cockpit.runtime.stubs import STUB_PROVIDERS

__all__ = [
    "STUB_PROVIDERS",
    "AgentRuntime",
    "ClaudeAgentRuntime",
    "MockAgentRuntime",
    "OllamaAgentRuntime",
    "OpenAIAgentRuntime",
    "ProviderUnavailable",
    "RuntimeEvent",
    "TurnResult",
    "get_runtime",
]


# Real, implemented providers and how to construct them (lazily, once).
_FACTORIES: dict[str, Callable[[], AgentRuntime]] = {
    "claude": ClaudeAgentRuntime,
    "mock": MockAgentRuntime,
    "openai": OpenAIAgentRuntime,
    "ollama": OllamaAgentRuntime,
}

_instances: dict[str, AgentRuntime] = {}


def get_runtime(provider: str) -> AgentRuntime:
    """Singleton per provider — interrupt/cancel must reach the same live instance."""
    if provider in _instances:
        return _instances[provider]
    factory = _FACTORIES.get(provider)
    if factory is not None:
        return _instances.setdefault(provider, factory())
    if provider in STUB_PROVIDERS:
        raise ProviderUnavailable(
            f"Provider “{provider}” is scaffolded but not implemented in the MVP."
        )
    raise ProviderUnavailable(f"Unknown provider “{provider}”.")
