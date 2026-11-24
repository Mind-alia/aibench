"""Registry of agent tools. Adding a tool: subclass Adapter in a new module and list it here (see docs/ADAPTERS.md)."""

from __future__ import annotations

from ..util import BenchError
from .antigravity import Antigravity
from .base import REVIEW, WORK, Adapter, Context, Invocation, Outcome, Usage
from .claude_code import ClaudeCode
from .codex import Codex
from .command import Command
from .fake import Fake
from .opencode import OpenCode

ADAPTERS: dict[str, type[Adapter]] = {cls.name: cls for cls in (ClaudeCode, Codex, Antigravity, OpenCode, Command, Fake)}


def get_adapter(name: str) -> Adapter:
    try:
        return ADAPTERS[name]()
    except KeyError:
        raise BenchError(f"unknown adapter {name!r}; known: {', '.join(sorted(ADAPTERS))}") from None


__all__ = ["ADAPTERS", "REVIEW", "WORK", "Adapter", "Context", "Invocation", "Outcome", "Usage", "get_adapter"]
