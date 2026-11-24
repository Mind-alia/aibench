"""Score a finished workspace with the task's checks, in a fresh copy the agent never saw, without any key."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .model import Check, Task
from .safety import check_env
from .util import copy_tree, execute, json_objects

CHECK_IGNORE = (".git", "__pycache__", ".pytest_cache", "*.pyc", ".DS_Store")


def run_checks(task: Task, workspace: Path, out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    return [run_check(task, check, workspace, out_dir) for check in task.checks]


def run_check(task: Task, check: Check, workspace: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aibench-check-") as tmp:
        work = Path(tmp) / "w"
        copy_tree(workspace, work, ignore=CHECK_IGNORE)
        for name in check.remove:
            for planted in work.rglob(name):
                if planted.is_file() or planted.is_symlink():
                    planted.unlink()
        if check.files:
            shutil.copytree(check.files, work / check.dest, dirs_exist_ok=True)
        command = check.command.replace("{task_dir}", "/task" if check.image else str(task.root))
        if check.image:
            argv = ["docker", "run", "--rm", "--network", "none", "-v", f"{work}:/work", "-v",
                    f"{task.root}:/task:ro", "-w", "/work"]
            for key, value in check.env.items():
                argv += ["-e", f"{key}={value}"]
            argv += [check.image, "sh", "-c", command]
            env = check_env()
        else:
            argv, env = ["/bin/sh", "-c", command], check_env(check.env)
        done = execute(argv, cwd=work, env=env, timeout_s=check.timeout_s)
        log = f"$ {command}\n--- exit {done.returncode}{' (timeout)' if done.timed_out else ''}\n{done.stdout}\n{done.stderr}"
        (out_dir / f"check-{check.name}.log").write_text(log, encoding="utf-8")
        passed, total, detail = parse_result(check, done.stdout, done.stderr, work)
    status = "timeout" if done.timed_out else ("ok" if total else "unparsed")
    return {"name": check.name, "primary": check is task.primary_check, "status": status, "passed": passed,
            "total": total, "rate": round(passed / total, 4) if total else None, "exit_code": done.returncode,
            "duration_s": round(done.duration_s, 1), "detail": detail}


def parse_result(check: Check, stdout: str, stderr: str, work: Path) -> tuple[int, int, dict]:
    if check.result == "json":
        data = _json_result(check, stdout, work)
        if data is None:
            return 0, 0, {"error": "no JSON result with the expected keys"}
        passed, total = _sum(data, check.passed_keys), _sum(data, check.total_keys)
        extra = {k: v for k, v in data.items() if k not in (*check.passed_keys, *check.total_keys)}
        return passed, total, extra
    if check.result == "junit":
        return _junit(work / check.junit)
    text = f"{stdout}\n{stderr}"
    return _pytest(text) if check.result == "pytest" else _unittest(text)


def _json_result(check: Check, stdout: str, work: Path) -> dict | None:
    if check.json_file:
        path = work / check.json_file
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    keys = (*check.passed_keys, *check.total_keys)
    return next((obj for obj in reversed(json_objects(stdout)) if all(_has(obj, k) for k in keys)), None)


def _has(data: dict, dotted: str) -> bool:
    value = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return True


def _get(data: dict, dotted: str):
    value = data
    for part in dotted.split("."):
        value = value[part]
    return value


def _sum(data: dict, keys: list[str]) -> int:
    total = 0
    for key in keys:
        value = _get(data, key)
        total += int(value) if not isinstance(value, bool) else int(value)
    return total


def _pytest(text: str) -> tuple[int, int, dict]:
    def count(word: str) -> int:
        found = re.findall(rf"(\d+) {word}", text)
        return int(found[-1]) if found else 0
    passed, failed, errors = count("passed"), count("failed"), count(r"errors?")
    return passed, passed + failed + errors, {"failed": failed, "errors": errors}


def _unittest(text: str) -> tuple[int, int, dict]:
    ran = re.findall(r"Ran (\d+) tests?", text)
    if not ran:
        return 0, 0, {"error": "no 'Ran N tests' line"}
    total = int(ran[-1])
    failures = sum(int(n) for n in re.findall(r"failures=(\d+)", text)[-1:])
    errors = sum(int(n) for n in re.findall(r"errors=(\d+)", text)[-1:])
    return total - failures - errors, total, {"failures": failures, "errors": errors}


def _junit(path: Path) -> tuple[int, int, dict]:
    # The report is written by the test run, not by a stranger; expat in Python 3.11+ does not fetch external
    # entities and limits entity expansion. A size cap keeps a runaway report out anyway (stdlib only, no defusedxml).
    try:
        if path.stat().st_size > 20 * 1024 * 1024:
            return 0, 0, {"error": "junit report larger than 20 MB"}
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        return 0, 0, {"error": f"junit report unreadable: {error}"}
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    tests = sum(int(s.get("tests", 0)) for s in suites)
    bad = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    total = tests - skipped
    return total - bad, total, {"skipped": skipped}
