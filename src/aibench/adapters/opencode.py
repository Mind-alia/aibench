"""opencode (`opencode run --format json`): one tool for many providers (OpenAI, Google, DeepSeek, Mistral,
OpenRouter, a local Ollama...). The model is written `provider/model`; the provider's key comes from your environment
(list its name in env_pass). opencode reports cost per step when it knows the provider's prices.

opencode has no sandbox of its own. Without `settings.auto_approve = true` it cannot run commands headless; with it, it
can run anything, so turn that on only with isolation = "docker".
"""

from __future__ import annotations

from ..util import json_objects, to_int
from .base import REVIEW, Adapter, Context, Invocation, Outcome, Usage, tail


class OpenCode(Adapter):
    name = "opencode"
    candidates = ("opencode", "/opt/homebrew/bin/opencode", "~/.opencode/bin/opencode")
    container_binary = "opencode"
    review_runs_commands = False  # no command without auto_approve, never on during reviews

    def build(self, config, ctx: Context, prefix):
        review = ctx.mode == REVIEW
        argv = [*prefix, "run", "--format", "json"]
        if config.settings.get("standalone", True):
            argv.append("--standalone")
        if config.model:
            argv += ["--model", config.model]
        if config.settings.get("auto_approve") and not review:
            argv.append("--auto")
        if config.settings.get("agent"):
            argv += ["--agent", str(config.settings["agent"])]
        argv += config.review_args if review else config.args
        argv.append(ctx.prompt)
        return Invocation(argv=argv, stdin=None)

    def parse(self, config, ctx, stdout, stderr, returncode):
        usage = Usage(models=[config.model] if config.model else [])
        cost, steps, texts, errors = 0.0, 0, [], []
        for event in json_objects(stdout):
            part = event.get("part") if isinstance(event.get("part"), dict) else event
            kind = str(part.get("type") or event.get("type") or "").replace("-", "_")
            if kind == "step_finish":
                steps += 1
                if isinstance(part.get("cost"), (int, float)):
                    cost += float(part["cost"])
                tokens = part.get("tokens") or {}
                cache = tokens.get("cache") or {}
                read, written = to_int(cache.get("read")), to_int(cache.get("write"))
                usage.input_tokens += to_int(tokens.get("input")) + read + written
                usage.output_tokens += to_int(tokens.get("output")) + to_int(tokens.get("reasoning"))
                usage.cache_read_tokens += read
                usage.cache_write_tokens += written
            elif kind == "text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
            elif kind == "error" or str(event.get("type")) == "error":
                errors.append(str(event.get("error") or part.get("error") or "error")[:300])
        usage.turns = steps or None
        if cost > 0:
            usage.cost_usd, usage.cost_source = round(cost, 6), "reported"
        error = "; ".join(errors)
        if returncode != 0 and not error:
            error = f"opencode exited with {returncode}: " + tail(stderr)
        return Outcome(ok=returncode == 0 and not errors, final_text=texts[-1] if texts else "", usage=usage,
                       error=error)
