"""What an agent and a check may see of your environment, and how secrets are kept out of the logs."""

from __future__ import annotations

import os

from .model import AgentConfig

# Enough for tools to find their binaries, their login (under HOME) and a terminal; nothing else leaks through.
BASE = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "TZ",
        "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME")
MIN_SECRET_LENGTH = 8


def agent_env(config: AgentConfig) -> dict[str, str]:
    """The environment of an agent: the base, the variables its config names in env_pass, its non-secret env."""
    env = {name: os.environ[name] for name in (*BASE, *config.env_pass) if name in os.environ}
    env.update(config.env)
    return env


def check_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment of a check: the base only, never a key, so scoring cannot spend money or phone home."""
    env = {name: os.environ[name] for name in BASE if name in os.environ}
    env.update(extra or {})
    return env


def secret_values(config: AgentConfig) -> list[str]:
    values = [os.environ.get(name, "") for name in config.env_pass]
    return sorted({v for v in values if len(v) >= MIN_SECRET_LENGTH}, key=len, reverse=True)


def redact(text: str, secrets: list[str]) -> str:
    for value in secrets:
        text = text.replace(value, "[REDACTED]")
    return text
