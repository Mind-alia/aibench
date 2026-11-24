"""One run: copy the task's starting code to a fresh folder outside the bench, let one agent work on it, keep what it
did (diff, final files, logs, usage), then score it with the hidden checks in another fresh copy."""

from __future__ import annotations

import hashlib
import json
import platform
import secrets
import shutil
import statistics
import tempfile
import time
from pathlib import Path

from . import __version__
from .adapters import WORK, Context, Outcome, get_adapter
from .model import AgentConfig, Task
from .pricing import apply as apply_prices
from .pricing import load_prices
from .project import Bench
from .safety import agent_env, check_env, redact, secret_values
from .scoring import run_checks
from .util import BenchError, copy_tree, execute, now_iso

GIT = ["git", "-c", "user.name=aibench", "-c", "user.email=aibench@localhost", "-c", "commit.gpgsign=false",
       "-c", "core.quotepath=off"]
SCHEMA = 1


def _git(args: list[str], cwd: Path, check: bool = True) -> str:
    done = execute([*GIT, *args], cwd=cwd, env=check_env(), timeout_s=600)
    if check and done.returncode != 0:
        raise BenchError(f"git {' '.join(args)} failed in {cwd}: {done.stderr.strip()[:300]}")
    return done.stdout


def prepare_workspace(task: Task, config: AgentConfig, base: Path) -> tuple[Path, str]:
    """Build the starting folder and commit it, so the diff shows only what the agent changed."""
    work = base / "work"
    if task.seed_git:
        repo, ref = str(task.seed_git["repo"]), task.seed_git.get("ref")
        clone = ["clone", "--quiet", "--no-hardlinks"]
        if task.seed_git.get("depth"):
            clone += ["--depth", str(task.seed_git["depth"])]
        if ref:
            clone += ["--branch", str(ref)]
        _git([*clone, repo, str(work)], base)
        _git(["remote", "remove", "origin"], work, check=False)
    elif task.seed:
        shutil.copytree(task.seed, work, symlinks=True)
    else:
        work.mkdir()
    if not (work / ".git").exists():
        _git(["init", "--quiet"], work)
    exclude = work / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8") as stream:  # caches never count as work done
        stream.write("\n__pycache__/\n*.pyc\n.pytest_cache/\n.mypy_cache/\n.ruff_cache/\n.venv/\nnode_modules/\n")
    for command in task.setup:
        done = execute(["/bin/sh", "-c", command], cwd=work, env=check_env(), timeout_s=1800)
        if done.returncode != 0:
            raise BenchError(f"task {task.id}: setup {command!r} failed: {(done.stderr or done.stdout)[-400:]}")
    for relative, content in config.workspace_files.items():
        target = work / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if content.startswith("@"):
            content = (config.path.parent / content[1:]).read_text(encoding="utf-8")
        target.write_text(content, encoding="utf-8")
    _git(["add", "-A"], work)
    _git(["commit", "--quiet", "--allow-empty", "--no-verify", "-m", "aibench: starting point"], work)
    return work, _git(["rev-parse", "HEAD"], work).strip()


def build_prompt(task: Task, config: AgentConfig) -> str:
    parts = [config.prompt_prefix.strip(), task.prompt.strip(), config.prompt_suffix.strip()]
    return "\n\n".join(p for p in parts if p) + "\n"


def docker_argv(config: AgentConfig, argv: list[str], work: Path, scratch: Path) -> list[str]:
    """Run the agent inside a container that sees only its workspace and scratch folder."""
    inner = [a.replace(str(work), "/work").replace(str(scratch), "/scratch") for a in argv]
    wrapped = ["docker", "run", "--rm", "-i", "--network", config.network, "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--memory", "4g", "--cpus", "2", "--pids-limit", "512",
               "-v", f"{work}:/work", "-v", f"{scratch}:/scratch", "-w", "/work"]
    for name in config.env_pass:
        wrapped += ["-e", name]
    for key, value in config.env.items():
        wrapped += ["-e", f"{key}={value}"]
    return [*wrapped, config.image, *inner]


def run_agent(config: AgentConfig, ctx: Context, log_dir: Path) -> tuple[Outcome, dict]:
    """Start the agent in ctx.workdir and read its answer. Shared by runs and reviews."""
    adapter = get_adapter(config.adapter)
    prefix = [adapter.container_binary] if config.isolation == "docker" else adapter.resolve(config)
    if not prefix:
        raise BenchError(f"config {config.id}: tool for adapter {config.adapter!r} not found; set binary = '...'")
    invocation = adapter.build(config, ctx, prefix)
    argv = invocation.argv
    if config.isolation == "docker":
        argv = docker_argv(config, argv, ctx.workdir, ctx.scratch)
    done = execute(argv, cwd=ctx.workdir, env=agent_env(config), stdin=invocation.stdin, timeout_s=ctx.timeout_s)
    hidden = secret_values(config)
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "agent.stdout").write_text(redact(done.stdout, hidden), encoding="utf-8")
    (log_dir / "agent.stderr").write_text(redact(done.stderr, hidden), encoding="utf-8")
    shown = [a if a != ctx.prompt else "<prompt>" for a in argv]
    (log_dir / "command.json").write_text(redact(json.dumps(shown, indent=1), hidden), encoding="utf-8")
    outcome = adapter.parse(config, ctx, done.stdout, done.stderr, done.returncode)
    outcome.final_text = redact(outcome.final_text, hidden)
    facts = {"returncode": done.returncode, "timed_out": done.timed_out, "duration_s": round(done.duration_s, 1)}
    if done.returncode is None and not done.timed_out:
        outcome.ok, outcome.error = False, done.stderr
    return outcome, facts


def _diff_numbers(work: Path, base_rev: str, run_dir: Path) -> dict:
    _git(["add", "-A"], work)
    patch = _git(["diff", "--cached", "--binary", base_rev], work, check=False)
    (run_dir / "diff.patch").write_text(patch, encoding="utf-8")
    files, added, removed = [], 0, 0
    for line in _git(["diff", "--cached", "--numstat", base_rev], work, check=False).splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            files.append(parts[2])
            added += int(parts[0]) if parts[0].isdigit() else 0
            removed += int(parts[1]) if parts[1].isdigit() else 0
    return {"files_changed": files, "lines_added": added, "lines_removed": removed}


def run_one(bench: Bench, task: Task, config: AgentConfig, *, budget_usd: float | None = None,
            label: str = "", keep_tmp: bool = False) -> dict:
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    run_dir = bench.runs_dir / task.id / config.id / run_id
    run_dir.mkdir(parents=True)
    record = {"schema": SCHEMA, "run_id": run_id, "task": task.id, "task_title": task.title, "config": config.id,
              "config_title": config.title, "family": config.family, "adapter": config.adapter,
              "provider": config.provider, "model": config.model, "effort": config.effort,
              "isolation": config.isolation, "label": label,
              "config_hash": hashlib.sha256(config.path.read_bytes()).hexdigest()[:12],
              "task_hash": hashlib.sha256(task.prompt.encode()).hexdigest()[:12], "started_at": now_iso(), "aibench": __version__,
              "host": platform.system(), "status": "error", "error": "", "notes": [], "checks": [],
              "primary": None, "usage": None, "cost_usd": None, "cost_source": "unknown", "duration_s": None}
    tmp = Path(tempfile.mkdtemp(prefix="aibench-"))
    try:
        work, base_rev = prepare_workspace(task, config, tmp)
        scratch = tmp / "scratch"
        scratch.mkdir()
        prompt = build_prompt(task, config)
        (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")
        ctx = Context(workdir=work, scratch=scratch, prompt=prompt, mode=WORK,
                      budget_usd=budget_usd if budget_usd is not None else config.budget_usd,
                      timeout_s=task.timeout_s)
        outcome, facts = run_agent(config, ctx, run_dir)
        usage = apply_prices(outcome.usage, config.model, load_prices(bench.pricing_file))
        record.update(duration_s=facts["duration_s"], usage=usage.as_dict(), cost_usd=usage.cost_usd,
                      cost_source=usage.cost_source, error=outcome.error, notes=outcome.notes,
                      status="timeout" if facts["timed_out"] else ("ok" if outcome.ok else "agent_error"))
        (run_dir / "final_message.md").write_text(outcome.final_text or "", encoding="utf-8")
        record.update(_diff_numbers(work, base_rev, run_dir))
        copy_tree(work, run_dir / "workspace")
        record["checks"] = run_checks(task, work, run_dir / "checks")
        primary = next((c for c in record["checks"] if c["primary"]), None)
        record["primary"] = ({"passed": primary["passed"], "total": primary["total"], "rate": primary["rate"]}
                             if primary else None)
    except BenchError as error:
        record["error"] = str(error)
    finally:
        record["finished_at"] = now_iso()
        (run_dir / "run.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
        if keep_tmp:
            record["notes"].append(f"temporary folder kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    return record


def load_runs(bench: Bench) -> list[dict]:
    runs = []
    if not bench.runs_dir.is_dir():
        return runs
    for path in sorted(bench.runs_dir.glob("*/*/*/run.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        record["_dir"] = str(path.parent)
        runs.append(record)
    return runs


def estimate_cost(runs: list[dict], config_id: str, fallback: float | None) -> float:
    known = [r["cost_usd"] for r in runs if r["config"] == config_id and isinstance(r.get("cost_usd"), (int, float))]
    if known:
        return statistics.median(known)
    return fallback or 0.0
