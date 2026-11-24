"""Command line: aibench list | doctor | run | campaign | review | calibrate | report."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .adapters import get_adapter
from .calibrate import calibrate
from .model import read_toml
from .project import Bench, load_bench
from .report import build, text_table, write
from .review import review_runs
from .runner import estimate_cost, load_runs, run_one
from .util import BenchError


def _money(value) -> str:
    return f"{value:.2f} $" if isinstance(value, (int, float)) else "cost unknown"


def _say_run(record: dict) -> None:
    primary = record.get("primary") or {}
    tests = f"{primary.get('passed')}/{primary.get('total')} hidden tests" if primary else "no check"
    minutes = f"{(record.get('duration_s') or 0) / 60:.1f} min"
    print(f"  {record['run_id']}  {record['status']:<11} {tests:<22} {_money(record.get('cost_usd')):<14} {minutes}"
          + (f"  ! {record['error'][:120]}" if record.get("error") else ""))


def cmd_list(bench: Bench, args) -> int:
    print(f"bench: {bench.root}\nruns:  {bench.runs_dir}\n\ntasks:")
    for task in bench.tasks.values():
        flags = " [calibration]" if task.calibration else ""
        print(f"  {task.id:<28} {task.title}{flags}")
    print("\nconfigs:")
    for config in bench.configs.values():
        state = "" if config.enabled else "  (disabled)"
        print(f"  {config.id:<28} {config.adapter:<12} {config.model or '(default model)'}{state}")
    return 0


def cmd_doctor(bench: Bench, args) -> int:
    print("tool check (nothing is sent to any model):")
    for config in bench.configs.values():
        adapter = get_adapter(config.adapter)
        prefix = adapter.resolve(config) if config.isolation == "host" else ["docker"]
        if prefix is None:
            state = "MISSING (install the tool or set binary = ...)"
        else:
            state = f"ok  {adapter.version(prefix) if config.isolation == 'host' else 'docker image ' + config.image}"
        keys = [name for name in config.env_pass if name not in os.environ]
        note = f"  needs {', '.join(keys)} in your environment" if keys else ""
        disabled = "  (disabled)" if not config.enabled else ""
        print(f"  {config.id:<28} {state}{note}{disabled}")
    return 0


def cmd_run(bench: Bench, args) -> int:
    task, config = bench.task(args.task), bench.config(args.config)
    print(f"{task.id} x {config.id}, {args.repeat} run(s)")
    for _ in range(args.repeat):
        record = run_one(bench, task, config, budget_usd=args.budget_usd, label=args.label, keep_tmp=args.keep_tmp)
        _say_run(record)
    return 0


def cmd_campaign(bench: Bench, args) -> int:
    path = Path(args.file).resolve()
    plan = read_toml(path)
    name = str(plan.get("name", path.stem))
    tasks = [bench.task(t) for t in plan.get("tasks", [])]
    configs = [bench.config(c) for c in plan.get("configs", [])]
    reviewers = [bench.config(r) for r in plan.get("reviewers", [])]
    repeat = int(plan.get("repeat", 3))
    cap = float(plan["budget_usd"]) if "budget_usd" in plan else None
    per_run = plan.get("per_run_budget_usd")
    if not tasks or not configs:
        raise BenchError(f"{path}: a campaign needs tasks = [...] and configs = [...]")
    planned = len(tasks) * len(configs) * repeat
    print(f"campaign {name}: {len(tasks)} task(s) x {len(configs)} config(s) x {repeat} = {planned} runs"
          + (f", cap {cap:.2f} $" if cap is not None else ", no cap"))
    if args.dry_run:
        for task in tasks:
            for config in configs:
                print(f"  would run {task.id} x {config.id} x {repeat}")
        return 0
    spent, history = 0.0, load_runs(bench)
    for _round in range(repeat):          # round-robin: every config gets its first run before any gets a second
        for task in tasks:
            for config in configs:
                if not config.enabled:
                    continue
                estimate = estimate_cost(history, config.id, per_run)
                if cap is not None and spent + estimate > cap:
                    print(f"  stop: {spent:.2f} $ spent, next run estimated {estimate:.2f} $, cap {cap:.2f} $")
                    return _campaign_reviews(bench, tasks, reviewers, name)
                record = run_one(bench, task, config, budget_usd=per_run, label=name)
                history.append(record)
                spent += record["cost_usd"] or 0.0
                print(f"{task.id} x {config.id}")
                _say_run(record)
    print(f"runs done, {spent:.2f} $ counted (runs with unknown cost count 0)")
    return _campaign_reviews(bench, tasks, reviewers, name)


def _campaign_reviews(bench: Bench, tasks, reviewers, name: str) -> int:
    runs = [r for r in load_runs(bench) if r.get("label") == name]
    for reviewer in reviewers:
        for task in tasks:
            for review in review_runs(bench, task, reviewer, runs, label=name):
                print(f"review {task.id} by {reviewer.id}: {review['status']} {_money(review.get('cost_usd'))}"
                      + (f"  ! {review['error'][:120]}" if review.get("error") else ""))
    data = build(bench, include_test=True)
    write(bench, data)
    print(text_table(data))
    return 0


def cmd_review(bench: Bench, args) -> int:
    task, reviewer = bench.task(args.task), bench.config(args.reviewer)
    runs = load_runs(bench)
    if args.label:
        runs = [r for r in runs if r.get("label") == args.label]
    results = review_runs(bench, task, reviewer, runs, again=args.again, group_size=args.group_size)
    if not results:
        print("nothing to review (no delivered run, or all already scored by this reviewer; --again to redo)")
    for review in results:
        scores = ", ".join(f"{run_id}: {score:g}" for run_id, score in review["scores"].items())
        print(f"{review['review_id']} {review['status']} {_money(review.get('cost_usd'))}  {scores}"
              + (f"  ! {review['error'][:160]}" if review.get("error") else ""))
    return 0


def cmd_calibrate(bench: Bench, args) -> int:
    task, reviewer = bench.task(args.task), bench.config(args.reviewer)
    result = calibrate(bench, task, reviewer, repeat=args.repeat, only=args.only, budget_usd=args.budget_usd,
                       timeout_s=int(args.timeout_min * 60))
    m = result["metrics"]

    def pct(value):
        return f"{100 * value:.0f}%" if value is not None else "-"
    print(f"calibration of {reviewer.id} on {task.id}: {m['answered']}/{m['calls']} answers")
    print(f"  planted defects caught:          {pct(m['defect_caught'])} (in both orders: {pct(m['defect_caught_both_orders'])})")
    print(f"  same verdict in both orders:     {pct(m['order_consistency'])}")
    print(f"  swayed by cosmetic changes:      {pct(m['cosmetic_swayed'])}")
    print(f"  first candidate wins:            {pct(m['first_slot_wins'])} (50% is neutral)")
    print(f"  cost:                            {_money(m['cost_usd'])}"
          + ("  (stopped: budget spent)" if result["stopped_on_budget"] else ""))
    return 0


def cmd_report(bench: Bench, args) -> int:
    data = build(bench, include_test=args.with_tests)
    report, dashboard = write(bench, data)
    print(text_table(data))
    print(f"\nreport: {report}\ndashboard: {dashboard.parent / 'index.html'} (open it in a browser)")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aibench", description="Benchmark AI coding agents and configurations.")
    p.add_argument("--version", action="version", version=f"aibench {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="tasks and configs found")
    sub.add_parser("doctor", help="check that each config's tool is installed")
    run = sub.add_parser("run", help="run one config on one task")
    run.add_argument("task")
    run.add_argument("config")
    run.add_argument("--repeat", type=int, default=1)
    run.add_argument("--budget-usd", type=float, help="cap per run, for tools that support one")
    run.add_argument("--label", default="", help="tag the runs (a campaign name)")
    run.add_argument("--keep-tmp", action="store_true", help="keep the temporary workspace for debugging")
    campaign = sub.add_parser("campaign", help="run a campaign file: tasks x configs x repeat, then reviews")
    campaign.add_argument("file")
    campaign.add_argument("--dry-run", action="store_true")
    review = sub.add_parser("review", help="blind review of a task's delivered runs")
    review.add_argument("task")
    review.add_argument("reviewer", help="a config id used as reviewer")
    review.add_argument("--label", default="")
    review.add_argument("--again", action="store_true")
    review.add_argument("--group-size", type=int, default=6)
    cal = sub.add_parser("calibrate", help="test a reviewer on the task's planted defects, in both orders")
    cal.add_argument("task")
    cal.add_argument("reviewer")
    cal.add_argument("--repeat", type=int, default=1)
    cal.add_argument("--only", nargs="*", help="variant names to use")
    cal.add_argument("--budget-usd", type=float, help="cap for the whole calibration (tools that report a cost)")
    cal.add_argument("--timeout-min", type=float, default=15, help="time limit of each comparison")
    report = sub.add_parser("report", help="summary table, report.json and dashboard data")
    report.add_argument("--with-tests", action="store_true", help="include the fake agent's runs")
    return p


COMMANDS = {"list": cmd_list, "doctor": cmd_doctor, "run": cmd_run, "campaign": cmd_campaign, "review": cmd_review,
            "calibrate": cmd_calibrate, "report": cmd_report}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        bench = load_bench()
        return COMMANDS[args.command](bench, args)
    except BenchError as error:
        print(f"aibench: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("aibench: interrupted", file=sys.stderr)
        return 130
