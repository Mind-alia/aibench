"""Small helpers shared by every module: errors, processes, copies, JSON in noisy output."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Folders never copied out of a workspace: version control, dependencies, caches.
HEAVY = (".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
         ".tox", "*.pyc", ".DS_Store")
# Files and folders an agent tool leaves behind; removed before a blind review so the tool cannot be guessed.
TOOL_TRACES = (".claude", ".codex", ".gemini", ".opencode", ".agy", ".antigravity", ".openhands", ".aider*",
               ".cursor", ".aibench", "CLAUDE.md", "AGENTS.md", "GEMINI.md", "CODEX.md")


class BenchError(Exception):
    """A problem the user can fix (bad config, missing task, missing tool); printed without a traceback."""


@dataclass
class Completed:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def execute(argv: list[str], *, cwd: Path, env: dict[str, str], stdin: str | None = None,
            timeout_s: float | None = None, limit: int = 20 * 1024 * 1024) -> Completed:
    """Run a command in its own process group; on timeout the whole group is stopped. Output goes through files."""
    with tempfile.TemporaryDirectory(prefix="aibench-io-") as io_dir:
        out_path, err_path = Path(io_dir, "out"), Path(io_dir, "err")
        started = time.monotonic()
        timed_out = False
        with out_path.open("wb") as out, err_path.open("wb") as err:
            try:
                proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=out, stderr=err,
                                        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                        start_new_session=True)
            except FileNotFoundError as error:
                return Completed(None, "", f"command not found: {error}", False, 0.0)
            try:
                if stdin is not None:
                    try:
                        proc.stdin.write(stdin.encode())
                        proc.stdin.close()
                    except BrokenPipeError:
                        pass
                proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                _stop_group(proc)
        duration = time.monotonic() - started
        return Completed(proc.returncode, _read(out_path, limit), _read(err_path, limit), timed_out, duration)


def _stop_group(proc: subprocess.Popen) -> None:
    for sig, wait in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def _read(path: Path, limit: int) -> str:
    with path.open("rb") as stream:
        data = stream.read(limit)
    return data.decode("utf-8", errors="replace")


def copy_tree(source: Path, dest: Path, *, ignore: tuple[str, ...] = HEAVY) -> None:
    shutil.copytree(source, dest, symlinks=True, ignore=shutil.ignore_patterns(*ignore), dirs_exist_ok=True)


def remove_traces(root: Path, keep: set[str] | None = None) -> list[str]:
    """Delete tool traces at the top of a copied workspace, except the files the task itself provided."""
    keep = keep or set()
    removed = []
    for pattern in TOOL_TRACES:
        for path in root.glob(pattern):
            name = path.name
            if name in keep:
                continue
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(name)
    return removed


def json_objects(text: str) -> list[dict]:
    """Every JSON object found in a text: one per line (JSONL) or several pretty-printed ones mixed with logs."""
    decoder = json.JSONDecoder()
    found, index, length = [], 0, len(text or "")
    while index < length:
        start = text.find("{", index)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            index = start + 1
            continue
        if isinstance(value, dict):
            found.append(value)
        index = end
    return found


def last_json_with(text: str, *keys: str) -> dict | None:
    """The last JSON object of a text that has at least one of the given keys."""
    for value in reversed(json_objects(text)):
        if any(key in value for key in keys):
            return value
    return None


def to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
