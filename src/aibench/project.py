"""Where a bench lives: aibench.toml (shared), aibench.local.toml (personal, ignored by Git), AIBENCH_TASKS."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from .model import AgentConfig, Task, load_config, load_task, read_toml
from .util import BenchError

ROOT_FILE = "aibench.toml"
LOCAL_FILE = "aibench.local.toml"


def find_root(start: Path | None = None) -> Path:
    env = os.environ.get("AIBENCH_ROOT")
    if env:
        root = Path(env).expanduser().resolve()
        if not (root / ROOT_FILE).is_file():
            raise BenchError(f"AIBENCH_ROOT={env} has no {ROOT_FILE}")
        return root
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / ROOT_FILE).is_file():
            return folder
    raise BenchError(f"no {ROOT_FILE} in {here} or above; run aibench inside a bench folder or set AIBENCH_ROOT")


@dataclass
class Bench:
    root: Path
    tasks_dirs: list[Path]
    configs_dirs: list[Path]
    runs_dir: Path
    pricing_file: Path | None

    @property
    def reviews_dir(self) -> Path:
        return self.runs_dir / "_reviews"

    @property
    def calibrations_dir(self) -> Path:
        return self.runs_dir / "_calibrations"

    @cached_property
    def tasks(self) -> dict[str, Task]:
        found: dict[str, Task] = {}
        for folder in self.tasks_dirs:
            if not folder.is_dir():
                continue
            for task_file in sorted(folder.glob("*/task.toml")):
                task = load_task(task_file)
                if task.id in found:
                    raise BenchError(f"task id {task.id!r} is defined twice ({found[task.id].root} and {task.root})")
                found[task.id] = task
        return found

    @cached_property
    def configs(self) -> dict[str, AgentConfig]:
        found: dict[str, AgentConfig] = {}
        for folder in self.configs_dirs:
            if not folder.is_dir():
                continue
            for config_file in sorted(folder.glob("*.toml")):
                config = load_config(config_file)
                if config.id in found:
                    raise BenchError(f"config id {config.id!r} is defined twice")
                found[config.id] = config
        return found

    def task(self, task_id: str) -> Task:
        try:
            return self.tasks[task_id]
        except KeyError:
            raise BenchError(f"unknown task {task_id!r}; known: {', '.join(sorted(self.tasks)) or 'none'}") from None

    def config(self, config_id: str) -> AgentConfig:
        try:
            return self.configs[config_id]
        except KeyError:
            raise BenchError(f"unknown config {config_id!r}; known: {', '.join(sorted(self.configs)) or 'none'}") from None


def _paths(root: Path, values, what: str, source: Path) -> list[Path]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise BenchError(f"{source}: {what} must be a list of paths")
    return [(root / Path(str(v)).expanduser()).resolve() for v in values]


def load_bench(start: Path | None = None) -> Bench:
    root = find_root(start)
    shared = read_toml(root / ROOT_FILE)
    local_file = root / LOCAL_FILE
    local = read_toml(local_file) if local_file.is_file() else {}
    tasks_dirs = _paths(root, shared.get("tasks_dirs", ["tasks"]), "tasks_dirs", root / ROOT_FILE)
    tasks_dirs += _paths(root, local.get("tasks_dirs"), "tasks_dirs", local_file)
    tasks_dirs += [Path(p).expanduser().resolve() for p in os.environ.get("AIBENCH_TASKS", "").split(os.pathsep) if p]
    configs_dirs = _paths(root, shared.get("configs_dirs", ["configs"]), "configs_dirs", root / ROOT_FILE)
    configs_dirs += _paths(root, local.get("configs_dirs"), "configs_dirs", local_file)
    runs_dir = (root / Path(str(local.get("runs_dir", shared.get("runs_dir", "runs")))).expanduser()).resolve()
    pricing = local.get("pricing_file", shared.get("pricing_file"))
    return Bench(
        root=root,
        tasks_dirs=list(dict.fromkeys(tasks_dirs)),
        configs_dirs=list(dict.fromkeys(configs_dirs)),
        runs_dir=runs_dir,
        pricing_file=(root / pricing).resolve() if pricing else None,
    )
