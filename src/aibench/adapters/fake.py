"""A stand-in agent for tests and dry runs: it copies a known solution and answers reviews by a fixed rule.

    [settings]
    solution = "../tasks/demo-invoice/calibration/reference"   # relative to the config file
    cost_usd = 0.01
    prefer = "longest"     # review rule: "longest" (more code wins) or "first" (always the first candidate)
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..util import last_json_with
from .base import REVIEW, Adapter, Context, Invocation, Outcome, Usage

AGENT = Path(__file__).resolve().parent.parent / "fake_agent.py"


class Fake(Adapter):
    name = "fake"
    container_binary = "python3"

    def resolve(self, config):
        return [sys.executable, "-I", str(AGENT)]

    def version(self, prefix):
        return "fake 1"

    def build(self, config, ctx: Context, prefix):
        argv = [*prefix, "--mode", ctx.mode, "--workdir", str(ctx.workdir)]
        if ctx.mode != REVIEW and config.settings.get("solution"):
            argv += ["--solution", str((config.path.parent / config.settings["solution"]).resolve())]
        argv += ["--cost", str(config.settings.get("cost_usd", 0.01)),
                 "--prefer", str(config.settings.get("prefer", "longest"))]
        return Invocation(argv=argv, stdin=ctx.prompt)

    def parse(self, config, ctx, stdout, stderr, returncode):
        answer = last_json_with(stdout, "fake")
        if answer is None:
            return Outcome(ok=False, error="fake agent printed nothing")
        usage = Usage(input_tokens=answer.get("input_tokens", 0), output_tokens=answer.get("output_tokens", 0),
                      cost_usd=answer.get("cost_usd"), cost_source="reported", turns=1, models=["fake"])
        return Outcome(ok=returncode == 0, final_text=answer.get("text", ""), usage=usage)
