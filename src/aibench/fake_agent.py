"""The fake agent started by the `fake` adapter. Work mode: copy a solution into the workspace. Review mode: read the
reviewer prompt on stdin and answer with the JSON it asks for, choosing by a fixed rule (no model involved)."""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="work")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--solution")
    parser.add_argument("--cost", type=float, default=0.01)
    parser.add_argument("--prefer", default="longest")
    args = parser.parse_args()
    prompt = sys.stdin.read()
    workdir = Path(args.workdir)
    if args.mode == "work":
        if args.solution:
            shutil.copytree(args.solution, workdir, dirs_exist_ok=True)
        text = "Copied the known solution."
    else:
        text = json.dumps(review(workdir, prompt, args.prefer))
    print(json.dumps({"fake": True, "text": text, "cost_usd": args.cost,
                      "input_tokens": len(prompt) // 4, "output_tokens": len(text) // 4}))
    return 0


def size(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*.py")) if folder.is_dir() else 0


def review(workdir: Path, prompt: str, prefer: str) -> dict:
    labels = re.findall(r"candidates/([A-Z])\b", prompt)
    labels = list(dict.fromkeys(labels)) or sorted(p.name for p in (workdir / "candidates").iterdir())
    sizes = {label: size(workdir / "candidates" / label) for label in labels}
    if prefer == "first":
        best = labels[0]
    else:
        best = max(labels, key=lambda label: (sizes[label], label))
    scores = {label: {"total": 30 if label == best else 20, "criteria": {}, "comment": "fake review"}
              for label in labels}
    return {"scores": scores, "winner": best, "ranking": sorted(labels, key=lambda l: -scores[l]["total"])}


if __name__ == "__main__":
    raise SystemExit(main())
