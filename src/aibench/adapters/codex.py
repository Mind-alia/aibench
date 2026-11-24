"""OpenAI Codex CLI (`codex exec --json`), with your ChatGPT login or OPENAI_API_KEY. It reports tokens, not dollars."""

from __future__ import annotations

from ..util import json_objects, to_int
from .base import REVIEW, Adapter, Context, Invocation, Outcome, Usage, tail

LAST_MESSAGE = "codex-last-message.txt"


class Codex(Adapter):
    name = "codex"
    candidates = (
        "codex",
        "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
        "/Applications/Codex.app/Contents/Resources/codex",
        "npx -y @openai/codex",
    )
    container_binary = "codex"

    def build(self, config, ctx: Context, prefix):
        review = ctx.mode == REVIEW
        argv = [*prefix, "exec", "--json", "--skip-git-repo-check", "--ephemeral", "-C", str(ctx.workdir),
                "-o", str(ctx.scratch / LAST_MESSAGE)]
        if config.settings.get("ignore_user_config", True):
            argv.append("--ignore-user-config")
        if config.isolation == "docker" and config.settings.get("bypass_sandbox_in_container"):
            argv.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            argv += ["--sandbox", "read-only" if review else "workspace-write",
                     "-c", "sandbox_workspace_write.network_access=false"]
        if config.model:
            argv += ["-m", config.model]
        if config.effort:
            argv += ["-c", f"model_reasoning_effort={config.effort}"]
        argv += config.review_args if review else config.args
        argv.append("-")  # the prompt comes on stdin
        return Invocation(argv=argv, stdin=ctx.prompt)

    def parse(self, config, ctx, stdout, stderr, returncode):
        usage = Usage(models=[config.model] if config.model else [])
        texts, errors, turns = [], [], 0
        for event in json_objects(stdout):
            kind = str(event.get("type", ""))
            if kind == "turn.completed":
                turns += 1
                numbers = event.get("usage") or {}
                usage.input_tokens += to_int(numbers.get("input_tokens"))
                usage.cache_read_tokens += to_int(numbers.get("cached_input_tokens"))
                usage.output_tokens += to_int(numbers.get("output_tokens"))
            elif kind == "item.completed":
                item = event.get("item") or {}
                if item.get("type") in ("agent_message", "assistant_message") and isinstance(item.get("text"), str):
                    texts.append(item["text"])
            elif kind in ("turn.failed", "error"):
                detail = event.get("error") or event.get("message") or kind
                errors.append(detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail))
        usage.turns = turns or None
        last_file = ctx.scratch / LAST_MESSAGE
        final = last_file.read_text(encoding="utf-8", errors="replace") if last_file.is_file() else ""
        final = final or (texts[-1] if texts else "")
        error = "; ".join(errors)[:500]
        if returncode != 0 and not error:
            error = f"codex exited with {returncode}: " + tail(stderr)
        return Outcome(ok=returncode == 0 and not errors, final_text=final, usage=usage, error=error)
