"""Tasks and agent configurations, read from TOML files and checked before anything runs."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .util import BenchError

ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
RESULT_FORMATS = ("json", "pytest", "unittest", "junit")
ISOLATIONS = ("host", "docker")
SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE)


def read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise BenchError(f"{path}: {error}") from error


def _check_id(value, path: Path) -> str:
    if not isinstance(value, str) or not ID.match(value):
        raise BenchError(f"{path}: id must be lowercase letters, digits, '.', '_' or '-' (got {value!r})")
    return value


def _strings(value, what: str, path: Path) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BenchError(f"{path}: {what} must be a list of strings")
    return list(value)


def _inside(root: Path, relative: str | None, what: str, path: Path, must_exist: bool = True) -> Path | None:
    if not relative:
        return None
    target = (root / relative).resolve()
    if must_exist and not target.exists():
        raise BenchError(f"{path}: {what} {relative!r} does not exist")
    return target


@dataclass
class Check:
    """A command that scores a finished workspace: hidden tests, a judge script, a measurement tool."""
    name: str
    command: str
    result: str = "json"
    files: Path | None = None
    dest: str = "_hidden_tests"
    junit: str = ""
    json_file: str = ""
    passed_keys: list[str] = field(default_factory=lambda: ["passed"])
    total_keys: list[str] = field(default_factory=lambda: ["total"])
    timeout_s: int = 900
    image: str = ""
    env: dict[str, str] = field(default_factory=dict)
    remove: list[str] = field(default_factory=lambda: ["sitecustomize.py", "usercustomize.py"])
    primary: bool = False


@dataclass
class Calibration:
    """A known-good solution and variants of it (planted defects, cosmetic changes) to test judges."""
    reference: Path
    variants: list[tuple[str, str, str, Path]]  # (name, kind, description, folder)


@dataclass
class Task:
    id: str
    title: str
    root: Path
    prompt: str
    description: str = ""
    seed: Path | None = None
    seed_git: dict | None = None
    setup: list[str] = field(default_factory=list)
    timeout_s: int = 1800
    checks: list[Check] = field(default_factory=list)
    rubric: str = ""
    max_score: int = 40
    tags: list[str] = field(default_factory=list)
    calibration: Calibration | None = None

    @property
    def primary_check(self) -> Check | None:
        return next((c for c in self.checks if c.primary), self.checks[0] if self.checks else None)


@dataclass
class AgentConfig:
    """One way of solving a task: a tool (adapter), a model, and the settings that go with them."""
    id: str
    title: str
    adapter: str
    path: Path
    model: str = ""
    effort: str = ""
    family: str = "agent"
    provider: str = ""
    binary: str = ""
    args: list[str] = field(default_factory=list)
    review_args: list[str] = field(default_factory=list)
    env_pass: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    budget_usd: float | None = None
    max_turns: int | None = None
    prompt_prefix: str = ""
    prompt_suffix: str = ""
    workspace_files: dict[str, str] = field(default_factory=dict)
    allowed_tools: list[str] | None = None
    disallowed_tools: list[str] | None = None
    isolation: str = "host"
    image: str = ""
    network: str = "bridge"
    enabled: bool = True
    notes: str = ""
    settings: dict = field(default_factory=dict)


def load_task(task_file: Path) -> Task:
    data = read_toml(task_file)
    root = task_file.parent.resolve()
    task_id = _check_id(data.get("id", root.name), task_file)
    prompt_path = _inside(root, data.get("prompt_file", "prompt.md"), "prompt_file", task_file)
    if prompt_path is None or not prompt_path.is_file():
        raise BenchError(f"{task_file}: a task needs a prompt file")
    seed_git = data.get("seed_git")
    if seed_git is not None and (not isinstance(seed_git, dict) or "repo" not in seed_git):
        raise BenchError(f"{task_file}: seed_git needs at least repo = '...'")
    rubric_path = _inside(root, data.get("rubric_file"), "rubric_file", task_file)
    checks = [_load_check(raw, root, task_file) for raw in data.get("checks", [])]
    if sum(c.primary for c in checks) > 1:
        raise BenchError(f"{task_file}: only one check can be primary")
    return Task(
        id=task_id,
        title=str(data.get("title", task_id)),
        root=root,
        prompt=prompt_path.read_text(encoding="utf-8"),
        description=str(data.get("description", "")),
        seed=_inside(root, data.get("seed"), "seed", task_file),
        seed_git=seed_git,
        setup=_strings(data.get("setup"), "setup", task_file),
        timeout_s=int(float(data.get("timeout_minutes", 30)) * 60),
        checks=checks,
        rubric=rubric_path.read_text(encoding="utf-8") if rubric_path else "",
        max_score=int(data.get("max_score", 40)),
        tags=_strings(data.get("tags"), "tags", task_file),
        calibration=_load_calibration(data.get("calibration"), root, task_file),
    )


def _keys(value, default: str) -> list[str]:
    if value is None:
        return [default]
    return [value] if isinstance(value, str) else list(value)


def _load_check(raw: dict, root: Path, task_file: Path) -> Check:
    if not isinstance(raw, dict) or not raw.get("name") or not raw.get("command"):
        raise BenchError(f"{task_file}: every [[checks]] needs a name and a command")
    result = raw.get("result", "json")
    if result not in RESULT_FORMATS:
        raise BenchError(f"{task_file}: check {raw['name']!r}: result must be one of {', '.join(RESULT_FORMATS)}")
    if result == "junit" and not raw.get("junit"):
        raise BenchError(f"{task_file}: check {raw['name']!r}: result 'junit' needs junit = 'path/to/report.xml'")
    return Check(
        name=str(raw["name"]),
        command=str(raw["command"]),
        result=result,
        files=_inside(root, raw.get("files"), "check files", task_file),
        dest=str(raw.get("dest", "_hidden_tests")),
        junit=str(raw.get("junit", "")),
        json_file=str(raw.get("json_file", "")),
        passed_keys=_keys(raw.get("passed_key"), "passed"),
        total_keys=_keys(raw.get("total_key"), "total"),
        timeout_s=int(raw.get("timeout_seconds", 900)),
        image=str(raw.get("image", "")),
        env={str(k): str(v) for k, v in (raw.get("env") or {}).items()},
        remove=_strings(raw.get("remove", ["sitecustomize.py", "usercustomize.py"]), "remove", task_file),
        primary=bool(raw.get("primary", False)),
    )


def _load_calibration(raw, root: Path, task_file: Path) -> Calibration | None:
    if not raw:
        return None
    reference = _inside(root, raw.get("reference"), "calibration reference", task_file)
    folder = _inside(root, raw.get("variants"), "calibration variants", task_file)
    if reference is None or folder is None:
        raise BenchError(f"{task_file}: [calibration] needs reference and variants")
    variants = []
    for meta in sorted(folder.glob("*.toml")):
        info = read_toml(meta)
        directory = meta.with_suffix("")
        kind = info.get("kind")
        if kind not in ("defect", "cosmetic") or not directory.is_dir():
            raise BenchError(f"{meta}: kind must be 'defect' or 'cosmetic', next to a folder {directory.name}/")
        variants.append((meta.stem, kind, str(info.get("description", "")), directory))
    variants.sort(key=lambda v: (v[1] != "defect", v[0]))  # planted defects first: they matter most
    return Calibration(reference=reference, variants=variants)


def load_config(config_file: Path) -> AgentConfig:
    data = read_toml(config_file)
    config_id = _check_id(data.get("id", config_file.stem), config_file)
    if not data.get("adapter"):
        raise BenchError(f"{config_file}: adapter is required (claude-code, codex, antigravity, opencode, command, fake)")
    env = {str(k): str(v) for k, v in (data.get("env") or {}).items()}
    for name in env:
        if SECRET_NAME.search(name):
            raise BenchError(f"{config_file}: {name} looks like a secret; keep it in your environment and list its "
                             f"name in env_pass instead of writing its value here")
    isolation = data.get("isolation", "host")
    if isolation not in ISOLATIONS:
        raise BenchError(f"{config_file}: isolation must be 'host' or 'docker'")
    if isolation == "docker" and not data.get("image"):
        raise BenchError(f"{config_file}: isolation 'docker' needs image = '...'")
    budget = data.get("budget_usd")
    return AgentConfig(
        id=config_id,
        title=str(data.get("title", config_id)),
        adapter=str(data["adapter"]),
        path=config_file.resolve(),
        model=str(data.get("model", "")),
        effort=str(data.get("effort", "")),
        family=str(data.get("family", "agent")),
        provider=str(data.get("provider", "")),
        binary=str(data.get("binary", "")),
        args=_strings(data.get("args"), "args", config_file),
        review_args=_strings(data.get("review_args"), "review_args", config_file),
        env_pass=_strings(data.get("env_pass"), "env_pass", config_file),
        env=env,
        budget_usd=float(budget) if budget is not None else None,
        max_turns=int(data["max_turns"]) if data.get("max_turns") else None,
        prompt_prefix=str(data.get("prompt_prefix", "")),
        prompt_suffix=str(data.get("prompt_suffix", "")),
        workspace_files={str(k): str(v) for k, v in (data.get("workspace_files") or {}).items()},
        allowed_tools=_strings(data["allowed_tools"], "allowed_tools", config_file) if "allowed_tools" in data else None,
        disallowed_tools=(_strings(data["disallowed_tools"], "disallowed_tools", config_file)
                          if "disallowed_tools" in data else None),
        isolation=isolation,
        image=str(data.get("image", "")),
        network=str(data.get("network", "bridge")),
        enabled=bool(data.get("enabled", True)),
        notes=str(data.get("notes", "")),
        settings=dict(data.get("settings") or {}),
    )
