"""Gather runs, reviews and calibrations into one report (JSON for the dashboard, a table for the terminal)."""

from __future__ import annotations

import json
import statistics
from itertools import combinations
from pathlib import Path

from . import __version__
from .calibrate import load_calibrations
from .project import Bench
from .review import load_reviews
from .runner import load_runs
from .util import now_iso

FEW_RUNS = 3


def _median(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.median(values), 4) if values else None


def _mean(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.fmean(values), 4) if values else None


def _family(record: dict, prefix: str = "") -> str:
    return record.get(f"{prefix}provider") or record.get(f"{prefix}adapter") or ""


def build(bench: Bench, include_test: bool = False) -> dict:
    """include_test: keep runs, reviews and calibrations of test configs (family "test", the fake agent)."""
    def real(config_id: str, family: str = "") -> bool:
        config = bench.configs.get(config_id)
        return include_test or (family or (config.family if config else "")) != "test"
    runs = [r for r in load_runs(bench) if real(r["config"], r.get("family", ""))]
    reviews = [r for r in load_reviews(bench) if r.get("status") == "ok" and real(r["reviewer"])]
    calibrations = [c for c in load_calibrations(bench) if real(c["reviewer"])]
    run_rows = [_run_row(r) for r in runs]
    by_id = {r["run_id"]: r for r in run_rows}
    for review in reviews:
        if review["mode"] != "score":
            continue
        for run_id, score in review["scores"].items():
            if run_id in by_id:
                by_id[run_id]["reviews"].append({"reviewer": review["reviewer"], "review_id": review["review_id"],
                                                 "pct": round(100 * score / review["max_score"], 1),
                                                 "score": score, "max": review["max_score"],
                                                 "defects": review.get("defects", {}).get(run_id, [])})
    for row in run_rows:
        row["review_pct"] = _mean([r["pct"] for r in row["reviews"]])
    summary = _summary(run_rows)
    tasks = sorted({r["task"] for r in run_rows} | set(bench.tasks))
    return {
        "generated_at": now_iso(),
        "aibench": __version__,
        "tasks": [_task_info(bench, t) for t in tasks],
        "configs": [_config_info(c) for c in bench.configs.values()],
        "runs": run_rows,
        "summary": summary,
        "best": _best(summary),
        "reviewers": _reviewers(bench, reviews, by_id, calibrations),
        "calibrations": [{k: c[k] for k in ("calibration_id", "task", "reviewer", "reviewer_model", "finished_at",
                                             "repeat", "metrics")} for c in calibrations],
    }


def _task_info(bench: Bench, task_id: str) -> dict:
    task = bench.tasks.get(task_id)
    if task is None:
        return {"id": task_id, "title": task_id, "description": "", "tags": [], "calibration": False}
    return {"id": task.id, "title": task.title, "description": task.description, "tags": task.tags,
            "max_score": task.max_score, "calibration": task.calibration is not None,
            "checks": [c.name for c in task.checks]}


def _config_info(config) -> dict:
    return {"id": config.id, "title": config.title, "adapter": config.adapter, "provider": config.provider,
            "model": config.model, "effort": config.effort, "family": config.family, "isolation": config.isolation,
            "enabled": config.enabled, "notes": config.notes}


def _run_row(record: dict) -> dict:
    usage = record.get("usage") or {}
    primary = record.get("primary") or {}
    return {
        "run_id": record["run_id"], "task": record["task"], "config": record["config"],
        "config_title": record.get("config_title", record["config"]), "family": record.get("family", ""),
        "adapter": record.get("adapter", ""), "provider": record.get("provider", ""), "model": record.get("model", ""),
        "label": record.get("label", ""), "config_hash": record.get("config_hash"),
        "started_at": record.get("started_at"), "status": record.get("status"),
        "error": (record.get("error") or "")[:300], "notes": record.get("notes", []),
        "passed": primary.get("passed"), "total": primary.get("total"), "rate": primary.get("rate"),
        "checks": [{k: c.get(k) for k in ("name", "status", "passed", "total", "rate")} for c in record.get("checks", [])],
        "cost_usd": record.get("cost_usd"), "cost_source": record.get("cost_source", "unknown"),
        "duration_s": record.get("duration_s"), "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"), "cache_read_tokens": usage.get("cache_read_tokens"),
        "turns": usage.get("turns"), "files_changed": len(record.get("files_changed", [])),
        "lines_added": record.get("lines_added"), "lines_removed": record.get("lines_removed"), "reviews": [],
    }


def _summary(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["task"], row["config"]), []).append(row)
    out = []
    for (task, config), group in sorted(groups.items()):
        delivered = [r for r in group if r["status"] == "ok"]
        rates = [r["rate"] for r in group if r["rate"] is not None]
        costs = [r["cost_usd"] for r in group if isinstance(r["cost_usd"], (int, float))]
        out.append({
            "task": task, "config": config, "config_title": group[0]["config_title"], "provider": group[0]["provider"],
            "model": group[0]["model"], "family": group[0]["family"], "runs": len(group), "delivered": len(delivered),
            "rate_median": _median(rates), "rate_min": min(rates) if rates else None,
            "rate_max": max(rates) if rates else None, "cost_median": _median(costs),
            "cost_min": min(costs) if costs else None, "cost_max": max(costs) if costs else None,
            "cost_known": len(costs), "duration_median": _median([r["duration_s"] for r in group]),
            "output_tokens_median": _median([r["output_tokens"] for r in group]),
            "review_pct": _mean([r["review_pct"] for r in group]),
            "review_reads": sum(len(r["reviews"]) for r in group), "indicative": len(group) < FEW_RUNS,
            "config_versions": len({r.get("config_hash") for r in group}),
        })
    return out


def _best(summary: list[dict]) -> list[dict]:
    best = []
    for task in sorted({s["task"] for s in summary}):
        rows = [s for s in summary if s["task"] == task and s["rate_median"] is not None]
        if not rows:
            continue
        top = max(s["rate_median"] for s in rows)
        leaders = [s for s in rows if s["rate_median"] == top]
        inf = float("inf")
        quality = max(leaders, key=lambda s: (s["review_pct"] if s["review_pct"] is not None else -1,
                                              -(s["cost_median"] if s["cost_median"] is not None else inf)))
        priced = [s for s in leaders if s["cost_median"] is not None]
        cheapest = min(priced, key=lambda s: s["cost_median"]) if priced else None
        best.append({"task": task, "top_rate": top, "best_quality": quality["config"],
                     "cheapest_at_top": cheapest["config"] if cheapest else None,
                     "indicative": any(s["indicative"] for s in leaders)})
    return best


def _concordance(reviews: list[dict], by_id: dict) -> float | None:
    """Share of run pairs, inside one review, where the reviewer ranks the run with more hidden tests passed higher."""
    agree = disagree = 0
    for review in reviews:
        scored = [(by_id[i]["rate"], s) for i, s in review["scores"].items() if i in by_id and by_id[i]["rate"] is not None]
        for (rate_a, score_a), (rate_b, score_b) in combinations(scored, 2):
            if rate_a == rate_b or score_a == score_b:
                continue
            if (rate_a > rate_b) == (score_a > score_b):
                agree += 1
            else:
                disagree += 1
    return round(agree / (agree + disagree), 3) if agree + disagree else None


def _self_preference(reviewer_id: str, family: str, rows: list[dict]) -> float | None:
    """How much more this reviewer likes runs of its own family than the other reviewers do (points out of 100)."""
    own, other = [], []
    for row in rows:
        mine = [r["pct"] for r in row["reviews"] if r["reviewer"] == reviewer_id]
        theirs = [r["pct"] for r in row["reviews"] if r["reviewer"] != reviewer_id]
        if not mine or not theirs:
            continue
        gap = statistics.fmean(mine) - statistics.fmean(theirs)
        (own if _family(row) == family else other).append(gap)
    if not own or not other:
        return None
    return round(statistics.fmean(own) - statistics.fmean(other), 1)


def _reviewers(bench: Bench, reviews: list[dict], by_id: dict, calibrations: list[dict]) -> list[dict]:
    out = []
    names = sorted({r["reviewer"] for r in reviews} | {c["reviewer"] for c in calibrations})
    for name in names:
        mine = [r for r in reviews if r["reviewer"] == name]
        scored = [r for r in mine if r["mode"] == "score"]
        config = bench.configs.get(name)
        family = (config.provider or config.adapter) if config else _family(mine[0], "reviewer_") if mine else ""
        latest: dict[str, dict] = {}
        for calibration in sorted((c for c in calibrations if c["reviewer"] == name), key=lambda c: c["finished_at"]):
            latest[calibration["task"]] = calibration["metrics"]
        cal = list(latest.values())
        out.append({
            "reviewer": name, "model": config.model if config else "", "family": family,
            "reviews": len(mine), "runs_scored": len({i for r in scored for i in r["scores"]}),
            "cost_per_review": _mean([r.get("cost_usd") for r in mine]),
            "agreement_with_tests": _concordance(scored, by_id),
            "self_preference": _self_preference(name, family, list(by_id.values())),
            "calibrated_tasks": len(cal),
            "defect_caught": _mean([m["defect_caught"] for m in cal]),
            "defect_caught_both_orders": _mean([m["defect_caught_both_orders"] for m in cal]),
            "order_consistency": _mean([m["order_consistency"] for m in cal]),
            "cosmetic_swayed": _mean([m["cosmetic_swayed"] for m in cal]),
            "first_slot_wins": _mean([m["first_slot_wins"] for m in cal]),
        })
    return out


def write(bench: Bench, data: dict) -> tuple[Path, Path]:
    bench.runs_dir.mkdir(parents=True, exist_ok=True)
    report = bench.runs_dir / "report.json"
    report.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    dashboard = bench.root / "dashboard" / "data.js"
    dashboard.parent.mkdir(parents=True, exist_ok=True)
    dashboard.write_text("window.AIBENCH_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    return report, dashboard


def text_table(data: dict) -> str:
    lines = []
    for task in data["tasks"]:
        rows = [s for s in data["summary"] if s["task"] == task["id"]]
        if not rows:
            continue
        lines.append(f"\n{task['title']} ({task['id']})")
        lines.append(f"  {'config':<24} {'runs':>4} {'tests':>7} {'review':>7} {'cost $':>8} {'min':>6}")
        for s in sorted(rows, key=lambda s: (-(s["rate_median"] or 0), s["cost_median"] or 1e9)):
            rate = f"{100 * s['rate_median']:.0f}%" if s["rate_median"] is not None else "-"
            review = f"{s['review_pct']:.0f}%" if s["review_pct"] is not None else "-"
            cost = f"{s['cost_median']:.2f}" if s["cost_median"] is not None else "?"
            minutes = f"{s['duration_median'] / 60:.1f}" if s["duration_median"] else "-"
            flag = "  (fewer than 3 runs)" if s["indicative"] else ""
            flag += "  (config file changed between runs)" if s["config_versions"] > 1 else ""
            lines.append(f"  {s['config']:<24} {s['runs']:>4} {rate:>7} {review:>7} {cost:>8} {minutes:>6}{flag}")
    for reviewer in data["reviewers"]:
        def pct(value):
            return f"{100 * value:.0f}%" if value is not None else "-"
        lines.append(f"\nreviewer {reviewer['reviewer']}: agrees with tests {pct(reviewer['agreement_with_tests'])}, "
                     f"catches planted defects {pct(reviewer['defect_caught'])}, "
                     f"same verdict both orders {pct(reviewer['order_consistency'])}")
    return "\n".join(lines) if lines else "no runs yet"
