"""Claude Code (`claude -p`), with your existing login or ANTHROPIC_API_KEY. It reports its own cost."""

from __future__ import annotations

from ..util import last_json_with, to_int
from .base import REVIEW, Adapter, Context, Invocation, Outcome, Usage, tail

WORK_TOOLS = [
    "Read", "Edit", "Write", "Glob", "Grep", "TodoWrite",
    "Bash(python3:*)", "Bash(python:*)", "Bash(pytest:*)", "Bash(uv:*)", "Bash(.venv/bin/python:*)",
    "Bash(node:*)", "Bash(npm test:*)", "Bash(npm run:*)",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(wc:*)", "Bash(mkdir:*)",
    "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)",
]
REVIEW_TOOLS = ["Read", "Glob", "Grep", "Bash(python3:*)", "Bash(python:*)", "Bash(ls:*)", "Bash(cat:*)"]
# No web access by default: an agent must not look the answer up, and a reviewer must not phone home.
DISALLOWED = ["WebFetch", "WebSearch"]


class ClaudeCode(Adapter):
    name = "claude-code"
    candidates = ("claude", "~/.local/bin/claude")
    container_binary = "claude"

    def build(self, config, ctx: Context, prefix):
        review = ctx.mode == REVIEW
        argv = [*prefix, "-p", "--output-format", "json", "--no-session-persistence", "--strict-mcp-config"]
        # Your own settings (plugins, hooks, memory) would change the result: load only the task's.
        argv += ["--setting-sources", str(config.settings.get("setting_sources", "project,local"))]
        if config.settings.get("bare"):
            argv.append("--bare")
        if config.model:
            argv += ["--model", config.model]
        if config.effort:
            argv += ["--effort", config.effort]
        if config.max_turns:
            argv += ["--max-turns", str(config.max_turns)]
        budget = ctx.budget_usd if ctx.budget_usd is not None else config.budget_usd
        if budget:
            argv += ["--max-budget-usd", f"{budget:g}"]
        if config.isolation == "docker" and config.settings.get("skip_permissions_in_container"):
            argv.append("--dangerously-skip-permissions")
        else:
            tools = REVIEW_TOOLS if review else (config.allowed_tools or WORK_TOOLS)
            argv += ["--permission-mode", "default" if review else "acceptEdits", "--allowedTools", ",".join(tools)]
        disallowed = config.disallowed_tools if config.disallowed_tools is not None else DISALLOWED
        if disallowed:
            argv += ["--disallowedTools", ",".join(disallowed)]
        argv += config.review_args if review else config.args
        return Invocation(argv=argv, stdin=ctx.prompt)

    def parse(self, config, ctx, stdout, stderr, returncode):
        result = last_json_with(stdout, "total_cost_usd", "is_error", "result")
        if result is None:
            return Outcome(ok=False, error="no JSON result from claude: " + tail(stderr or stdout))
        usage = Usage(cost_usd=result.get("total_cost_usd"), cost_source="reported", turns=result.get("num_turns"))
        if usage.cost_usd is None:
            usage.cost_source = "unknown"
        per_model = result.get("modelUsage") or {}
        if per_model:
            for name, numbers in per_model.items():
                usage.models.append(name)
                fresh = to_int(numbers.get("inputTokens"))
                read = to_int(numbers.get("cacheReadInputTokens"))
                written = to_int(numbers.get("cacheCreationInputTokens"))
                usage.input_tokens += fresh + read + written
                usage.cache_read_tokens += read
                usage.cache_write_tokens += written
                usage.output_tokens += to_int(numbers.get("outputTokens"))
        else:
            numbers = result.get("usage") or {}
            read = to_int(numbers.get("cache_read_input_tokens"))
            written = to_int(numbers.get("cache_creation_input_tokens"))
            usage.input_tokens = to_int(numbers.get("input_tokens")) + read + written
            usage.cache_read_tokens, usage.cache_write_tokens = read, written
            usage.output_tokens = to_int(numbers.get("output_tokens"))
        error = ""
        if result.get("is_error") or result.get("subtype") not in (None, "success"):
            error = f"claude stopped: {result.get('subtype') or 'error'}"
        text = result.get("result") if isinstance(result.get("result"), str) else ""
        return Outcome(ok=not error and returncode == 0, final_text=text, usage=usage, error=error)
