"""Provider-neutral agent runtimes."""

from cockpit.runtime.base import AgentRuntime, ProviderUnavailable, RuntimeEvent, TurnResult
from cockpit.runtime.claude import ClaudeAgentRuntime
from cockpit.runtime.mock import MockAgentRuntime
from cockpit.runtime.stubs import STUB_PROVIDERS

__all__ = [
    "STUB_PROVIDERS",
    "AgentRuntime",
    "ClaudeAgentRuntime",
    "MockAgentRuntime",
    "ProviderUnavailable",
    "RuntimeEvent",
    "TurnResult",
    "get_runtime",
]


_instances: dict[str, AgentRuntime] = {}


def get_runtime(provider: str) -> AgentRuntime:
    """Singleton per provider — interrupt/cancel must reach the same live instance."""
    if provider in _instances:
        return _instances[provider]
    if provider == "claude":
        return _instances.setdefault(provider, ClaudeAgentRuntime())
    if provider == "mock":
        return _instances.setdefault(provider, MockAgentRuntime())
    if provider in STUB_PROVIDERS:
        raise ProviderUnavailable(
            f"Provider “{provider}” is scaffolded but not implemented in the MVP."
        )
    raise ProviderUnavailable(f"Unknown provider “{provider}”.")
