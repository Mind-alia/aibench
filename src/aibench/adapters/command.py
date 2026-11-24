"""Any other agent CLI (Gemini CLI, aider, OpenHands, DeepSeek Harness, a script of yours), described in its config.

    [settings]
    command = ["mytool", "--model", "{model}", "--message-file", "{prompt_file}"]
    review_command = [...]           # optional, for read-only reviews
    stdin = false                    # true: the prompt is also sent on stdin
    final_text = "stdout"            # or "file:{scratch}/answer.md"
    cost_regex = 'Cost: \\$([0-9.]+)'          # optional, last match wins
    input_tokens_regex = 'Tokens in: ([0-9]+)'
    output_tokens_regex = 'Tokens out: ([0-9]+)'

Placeholders: {model} {effort} {prompt} {prompt_file} {workdir} {scratch} {budget_usd}.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from ..util import BenchError
from .base import REVIEW, Adapter, Context, Invocation, Outcome, Usage, tail

PROMPT_FILE = "prompt.md"


class Command(Adapter):
    name = "command"

    def resolve(self, config):
        command = config.settings.get("command")
        if not isinstance(command, list) or not command:
            return None
        return super().resolve(replace(config, binary=config.binary or str(command[0])))

    def build(self, config, ctx: Context, prefix):
        template = config.settings.get("review_command") if ctx.mode == REVIEW else None
        template = template or config.settings.get("command")
        if not isinstance(template, list) or not template:
            raise BenchError(f"{config.path}: settings.command must be a non-empty list")
        prompt_file = ctx.scratch / PROMPT_FILE
        prompt_file.write_text(ctx.prompt, encoding="utf-8")
        values = {"model": config.model, "effort": config.effort, "prompt": ctx.prompt,
                  "prompt_file": str(prompt_file), "workdir": str(ctx.workdir), "scratch": str(ctx.scratch),
                  "budget_usd": "" if ctx.budget_usd is None else f"{ctx.budget_usd:g}"}
        argv = [_fill(part, values) for part in template]
        argv[0] = prefix[0]
        argv += config.review_args if ctx.mode == REVIEW else config.args
        return Invocation(argv=argv, stdin=ctx.prompt if config.settings.get("stdin") else None)

    def parse(self, config, ctx, stdout, stderr, returncode):
        both = f"{stdout}\n{stderr}"
        usage = Usage(models=[config.model] if config.model else [])
        cost = _last(config.settings.get("cost_regex"), both)
        if cost is not None:
            usage.cost_usd, usage.cost_source = float(cost), "reported"
        usage.input_tokens = int(float(_last(config.settings.get("input_tokens_regex"), both) or 0))
        usage.output_tokens = int(float(_last(config.settings.get("output_tokens_regex"), both) or 0))
        source = str(config.settings.get("final_text", "stdout"))
        if source.startswith("file:"):
            path = Path(_fill(source[5:], {"scratch": str(ctx.scratch), "workdir": str(ctx.workdir)}))
            final = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        else:
            final = stdout
        error = "" if returncode == 0 else f"exited with {returncode}: " + tail(stderr)
        return Outcome(ok=returncode == 0, final_text=final, usage=usage, error=error)


def _fill(text: str, values: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), text)


def _last(pattern, text: str) -> str | None:
    if not pattern:
        return None
    matches = re.findall(pattern, text)
    if not matches:
        return None
    last = matches[-1]
    return last[0] if isinstance(last, tuple) else last
