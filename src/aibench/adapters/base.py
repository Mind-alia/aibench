"""The contract between the runner and one agent tool: how to start it, how to read what it says back."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..model import AgentConfig

WORK, REVIEW = "work", "review"


@dataclass
class Usage:
    input_tokens: int = 0          # every input token, cached ones included
    output_tokens: int = 0
    cache_read_tokens: int = 0     # part of the input read from cache
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    cost_source: str = "unknown"   # reported (by the tool) | priced (pricing.toml) | unknown
    turns: int | None = None
    models: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Outcome:
    ok: bool
    final_text: str = ""
    usage: Usage = field(default_factory=Usage)
    error: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class Context:
    workdir: Path       # where the agent works (review: the folder holding the candidates)
    scratch: Path       # private to the runner, outside workdir: last-message files and the like
    prompt: str
    mode: str = WORK
    budget_usd: float | None = None
    timeout_s: int = 1800


@dataclass
class Invocation:
    argv: list[str]
    stdin: str | None = None


class Adapter:
    name = "base"
    #: Commands or absolute paths tried in order when the config does not set `binary`.
    candidates: tuple[str, ...] = ()
    #: Name of the tool inside a container (isolation = "docker").
    container_binary = ""
    #: Arguments that print a version.
    version_args: tuple[str, ...] = ("--version",)
    #: Whether the tool can run commands (tests, small probes) while it reviews read-only.
    review_runs_commands = True

    def resolve(self, config: AgentConfig) -> list[str] | None:
        """The command prefix that starts the tool, or None when it is not installed."""
        if config.binary:
            parts = config.binary.split()
            if not _runnable(parts[0]):
                return None
            return [shutil.which(os.path.expanduser(parts[0])) or os.path.expanduser(parts[0]), *parts[1:]]
        for candidate in self.candidates:
            parts = candidate.split()
            if _runnable(parts[0]):
                return [shutil.which(parts[0]) or os.path.expanduser(parts[0]), *parts[1:]]
        return None

    def version(self, prefix: list[str]) -> str:
        try:
            done = subprocess.run([*prefix, *self.version_args], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return (done.stdout or done.stderr).strip().splitlines()[0][:120] if (done.stdout or done.stderr) else ""

    def build(self, config: AgentConfig, ctx: Context, prefix: list[str]) -> Invocation:
        raise NotImplementedError

    def parse(self, config: AgentConfig, ctx: Context, stdout: str, stderr: str, returncode: int | None) -> Outcome:
        raise NotImplementedError


def _runnable(command: str) -> bool:
    path = os.path.expanduser(command)
    if os.sep in path:
        return os.path.isfile(path) and os.access(path, os.X_OK)
    return shutil.which(path) is not None


def tail(text: str, lines: int = 12) -> str:
    return "\n".join((text or "").strip().splitlines()[-lines:])[:2000]
