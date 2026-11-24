"""Google Antigravity CLI (`agy -p`), with your Google login. Headless, it refuses every shell command unless allowed.

By default the agent can read and write files but cannot run commands (so it cannot run its own tests). To let it run
some, list them in the config: `settings.allow_commands = ["python3", "pytest"]` becomes a session-only
`permissions.allow` rule passed with `--settings`; nothing is saved in your Antigravity settings. That choice is yours.
"""

from __future__ import annotations

import json

from ..util import json_objects, to_int
from .base import REVIEW, Adapter, Context, Invocation, Outcome, Usage, tail

TOKEN_NAMES = {
    "input": ("input_tokens", "inputTokens", "prompt_tokens", "promptTokens", "promptTokenCount"),
    "output": ("output_tokens", "outputTokens", "completion_tokens", "completionTokens", "candidatesTokenCount"),
    "cached": ("cached_tokens", "cachedTokens", "cache_read_tokens", "cachedContentTokenCount"),
}


class Antigravity(Adapter):
    name = "antigravity"
    candidates = ("agy", "~/.local/bin/agy")
    container_binary = "agy"
    review_runs_commands = False  # headless plan mode refuses every command

    def build(self, config, ctx: Context, prefix):
        review = ctx.mode == REVIEW
        argv = [*prefix, "-p", ctx.prompt, "--output-format", "json", "--mode", "plan" if review else "accept-edits",
                "--print-timeout", f"{int(ctx.timeout_s)}s"]
        if config.settings.get("sandbox", True):
            argv.append("--sandbox")
        if config.model:
            argv += ["--model", config.model]
        if config.effort:
            argv += ["--effort", config.effort]
        allowed = [] if review else list(config.settings.get("allow_commands") or [])
        if allowed:
            rules = [f"command({name})" for name in allowed]
            argv += ["--settings", json.dumps({"permissions": {"allow": rules}})]
        argv += config.review_args if review else config.args
        return Invocation(argv=argv, stdin=None)

    def parse(self, config, ctx, stdout, stderr, returncode):
        envelope = next((e for e in reversed(json_objects(stdout)) if "status" in e or "response" in e), None)
        if envelope is None:
            return Outcome(ok=False, error="no JSON envelope from agy: " + tail(stderr or stdout))
        denied = [str((a.get("display_name") or a.get("name")) if isinstance(a, dict) else a)
                  for a in envelope.get("denied_actions") or []]
        usage = Usage(models=[config.model] if config.model else [])
        numbers = _usage_block(envelope)
        if numbers:
            usage.input_tokens = _first(numbers, TOKEN_NAMES["input"])
            usage.output_tokens = _first(numbers, TOKEN_NAMES["output"])
            usage.cache_read_tokens = _first(numbers, TOKEN_NAMES["cached"])
        if isinstance(envelope.get("num_turns"), int):
            usage.turns = envelope["num_turns"]
        status = envelope.get("status")
        response = envelope.get("response") if isinstance(envelope.get("response"), str) else ""
        notes = [f"denied: {name}" for name in denied]
        error = "" if status == "SUCCESS" else f"agy status {status!r}: {envelope.get('error') or ''}"[:300]
        return Outcome(ok=status == "SUCCESS" and returncode == 0, final_text=response, usage=usage, error=error,
                       notes=notes)


def _usage_block(envelope: dict) -> dict:
    for key in ("usage", "token_usage", "tokens", "stats", "usageMetadata"):
        value = envelope.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _first(numbers: dict, names: tuple[str, ...]) -> int:
    for name in names:
        if name in numbers:
            return to_int(numbers[name])
    return 0
