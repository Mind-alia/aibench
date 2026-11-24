# Configurations and adapters

## A configuration

```toml
title = "Claude Code + Sonnet"
adapter = "claude-code"           # claude-code | codex | antigravity | opencode | command | fake
provider = "anthropic"            # used to spot a reviewer judging its own family
model = "sonnet"                  # empty: the tool's default
effort = "high"                   # passed to tools that have one
family = "model-alone"            # free label for the dashboard: model-alone, harness, factory...
budget_usd = 5                    # per run, for tools that can stop themselves (Claude Code)
max_turns = 200
prompt_prefix = "Work in small steps and run the tests often."
prompt_suffix = ""
workspace_files = { "CLAUDE.md" = "@instructions/short.md" }   # dropped in before the agent starts ('@' = file)
env_pass = ["ANTHROPIC_API_KEY"]  # names only: values stay in your environment
env = { SOME_FLAG = "1" }         # non-secret variables
allowed_tools = ["Read", "Edit", "Bash(python3:*)"]   # Claude Code only
disallowed_tools = ["WebFetch", "WebSearch"]
args = ["--extra", "flag"]        # appended to the command (work)
review_args = []                  # appended when the config reviews
isolation = "host"                # or "docker" with image = "..." and network = "bridge" | "none"
enabled = true
notes = "Shown by aibench list and the dashboard."

[settings]                        # adapter-specific, below
```

## Adapter settings

| Adapter | Settings |
|---|---|
| `claude-code` | `setting_sources` (default `"project,local"`: your user settings and plugins are not loaded), `bare` (true needs an API key), `skip_permissions_in_container` |
| `codex` | `ignore_user_config` (default true), `bypass_sandbox_in_container` |
| `antigravity` | `sandbox` (default true), `allow_commands` (list of binaries, session-only rule) |
| `opencode` | `standalone` (default true), `auto_approve` (only in a container), `agent` |
| `command` | `command`, `review_command`, `stdin`, `final_text`, `cost_regex`, `input_tokens_regex`, `output_tokens_regex` |
| `fake` | `solution`, `cost_usd`, `prefer` |

## Adding an adapter

Write a subclass of `aibench.adapters.base.Adapter` with:

- `name`, `candidates` (commands or paths tried in order), `container_binary`;
- `build(config, ctx, prefix)`: the command line and stdin for `ctx.mode` `"work"` or `"review"` (review must be
  read-only);
- `parse(config, ctx, stdout, stderr, returncode)`: an `Outcome` with `ok`, `final_text`, `usage` (tokens, and
  `cost_usd` with `cost_source = "reported"` when the tool gives one) and `error`.

Register it in `aibench/adapters/__init__.py` and add a test that parses a real output sample of the tool. Before
writing one, check whether the `command` adapter is enough.
