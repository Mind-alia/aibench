"""Check a judge before trusting it. For a task with a calibration set, the reviewer compares the known-good reference
with each variant, in both orders:

- a *defect* variant (a planted bug) must lose, whatever its position;
- a *cosmetic* variant (same behaviour, other names) should tie or split, not win or lose consistently;
- the verdict must not depend on which candidate is shown first.
"""

from __future__ import annotations

import json
import secrets
import tempfile
import time
from pathlib import Path

from .model import AgentConfig, Task
from .project import Bench
from .review import blind_review, build_from_overlay
from .util import BenchError, now_iso

REFERENCE = "reference"


def calibrate(bench: Bench, task: Task, reviewer: AgentConfig, *, repeat: int = 1, only: list[str] | None = None,
              budget_usd: float | None = None, timeout_s: int = 900) -> dict:
    """budget_usd caps the whole calibration: no comparison starts once it is spent, and each one gets at most what is
    left. Comparisons go variant by variant, both orders together, so a stop still leaves complete pairs."""
    if task.calibration is None:
        raise BenchError(f"task {task.id} has no [calibration] set")
    variants = [v for v in task.calibration.variants if not only or v[0] in only]
    if not variants:
        raise BenchError(f"task {task.id}: no calibration variant selected")
    verdicts, spent, stopped = [], 0.0, False
    with tempfile.TemporaryDirectory(prefix="aibench-calibration-") as tmp:
        folders = {REFERENCE: build_from_overlay(task, task.calibration.reference, Path(tmp) / REFERENCE)}
        for name, _kind, _description, overlay in variants:
            folders[name] = build_from_overlay(task, overlay, Path(tmp) / name)
        for round_index in range(repeat):
            for name, kind, _description, _overlay in variants:
                pair = {REFERENCE: folders[REFERENCE], name: folders[name]}
                if budget_usd is not None and spent >= budget_usd:
                    stopped = True
                    break
                for first in (REFERENCE, name):
                    order = [first, name if first == REFERENCE else REFERENCE]
                    left = None if budget_usd is None else max(budget_usd - spent, 0.01)
                    per_call = left if reviewer.budget_usd is None or left is None else min(left, reviewer.budget_usd)
                    review = blind_review(bench, task, reviewer, pair, mode="pair", order=order,
                                          label=f"calibration:{task.id}", timeout_s=timeout_s, budget_usd=per_call)
                    spent += review.get("cost_usd") or 0.0
                    verdicts.append({"variant": name, "kind": kind, "round": round_index, "first": first,
                                     "winner": review.get("winner"), "status": review["status"],
                                     "review_id": review["review_id"], "cost_usd": review.get("cost_usd"),
                                     "duration_s": review.get("duration_s"), "error": review.get("error", "")})
    result = {"calibration_id": f"{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}", "task": task.id,
              "reviewer": reviewer.id, "reviewer_adapter": reviewer.adapter, "reviewer_model": reviewer.model,
              "reviewer_provider": reviewer.provider, "finished_at": now_iso(), "repeat": repeat,
              "budget_usd": budget_usd, "spent_usd": round(spent, 4), "stopped_on_budget": stopped,
              "verdicts": verdicts, "metrics": metrics(verdicts)}
    out = bench.calibrations_dir / task.id / reviewer.id
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{result['calibration_id']}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False),
                                                          encoding="utf-8")
    return result


def metrics(verdicts: list[dict]) -> dict:
    """Numbers that say whether a judge can be trusted on this task (None when there is nothing to measure)."""
    answered = [v for v in verdicts if v["status"] == "ok" and v["winner"]]
    defects = [v for v in answered if v["kind"] == "defect"]
    pairs: dict[tuple[str, int], list[dict]] = {}
    for v in answered:
        pairs.setdefault((v["variant"], v["round"]), []).append(v)
    both = [p for p in pairs.values() if len(p) == 2]
    consistent = [p for p in both if p[0]["winner"] == p[1]["winner"]]
    defect_pairs = [p for p in both if p[0]["kind"] == "defect"]
    cosmetic_pairs = [p for p in both if p[0]["kind"] == "cosmetic"]
    decided = [v for v in answered if v["winner"] != "tie"]
    first_wins = [v for v in decided if v["winner"] == v["first"]]
    costs = [v["cost_usd"] for v in verdicts if isinstance(v.get("cost_usd"), (int, float))]

    def share(part, whole):
        return round(len(part) / len(whole), 3) if whole else None

    return {
        "calls": len(verdicts),
        "answered": len(answered),
        "defect_caught": share([v for v in defects if v["winner"] == REFERENCE], defects),
        "defect_caught_both_orders": share([p for p in defect_pairs if all(v["winner"] == REFERENCE for v in p)],
                                           defect_pairs),
        "order_consistency": share(consistent, both),
        "cosmetic_swayed": share([p for p in cosmetic_pairs if p[0]["winner"] == p[1]["winner"] != "tie"],
                                 cosmetic_pairs),
        "first_slot_wins": share(first_wins, decided),
        "cost_usd": round(sum(costs), 4) if costs else None,
        "cost_known_calls": len(costs),
    }


def load_calibrations(bench: Bench) -> list[dict]:
    found = []
    if not bench.calibrations_dir.is_dir():
        return found
    for path in sorted(bench.calibrations_dir.glob("*/*/*.json")):
        try:
            found.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return found
