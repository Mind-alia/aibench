# Security model

aibench starts AI agents that write and run code on your machine. This page says what protects you and where the
limits are.

## What aibench does

- **Fresh workspace outside the bench.** Each run works in a new temporary folder (`$TMPDIR/aibench-*`), never inside
  this repository, so the agent does not start next to the hidden tests or other runs.
- **Hidden tests arrive last.** Checks copy the finished work into another fresh folder, delete planted
  `sitecustomize.py`/`usercustomize.py`, add the hidden files, and only then run. The demo runs its tests with
  `python3 -I` so the workspace cannot change the interpreter.
- **Keys only where named.** An agent receives a minimal environment (`PATH`, `HOME`, locale, temp dir) plus the
  variables its config lists in `env_pass`. Checks receive no key at all. Values of `env_pass` variables are replaced by
  `[REDACTED]` in every saved log. A config that writes a secret-looking variable in clear is refused.
- **Reviewers are read-only.** Claude Code reviews with read tools only, Codex with `--sandbox read-only`, Antigravity
  with `--mode plan`.
- **No web search by default** for Claude Code agents (`WebFetch` and `WebSearch` are disallowed), so an agent does not
  look the answer up.

## What each tool adds on the host

| Tool | Default protection in aibench |
|---|---|
| Claude Code | `acceptEdits` plus an allow-list of commands (Python, tests, read-only git); anything else is refused headless |
| Codex CLI | its own sandbox: writes only in the workspace, network off |
| Antigravity | `--sandbox`; no shell command unless you allow some with `settings.allow_commands` (session only) |
| opencode | no sandbox: without `auto_approve` it cannot run commands; with it, use `isolation = "docker"` |
| command | whatever the tool does: read its docs |

## Limits

- In host mode an agent can usually **read** files elsewhere on your disk (Codex's sandbox allows reads, for example).
  For private task packs whose hidden tests must stay unseen, or for agents allowed to run anything, use
  `isolation = "docker"`: the container sees only the workspace and a scratch folder, with dropped capabilities,
  `no-new-privileges`, and memory, CPU and process limits.
- `--dangerously-skip-permissions` (Claude Code) and `--dangerously-bypass-approvals-and-sandbox` (Codex) are only
  used inside a container, and only when the config asks for it.
- Checks with `image = ...` run in a container with the network off; checks without an image run on the host in a
  temporary folder.

## Reporting a problem

Please open a private security advisory on the repository rather than a public issue.
