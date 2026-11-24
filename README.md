# aibench

**Benchmark AI coding agents, and the way you configure them, on your own tasks.**

Public leaderboards say which model is strong in general. They do not say which combination of *tool + model +
instructions* does your kind of work best, or at what cost. aibench runs that comparison on tasks you choose. It scores
each result with hidden tests the agent never saw, has the code blind-reviewed by another model, and checks that
reviewer before you trust it.

```
task × configuration × repeat  →  run  →  hidden tests  →  blind review  →  report + dashboard
                                                        ↑
                                     judge calibration (planted defects, order swap)
```

## What it measures

| Measure | Where it comes from |
|---|---|
| Hidden tests passed | the task's checks, run in a fresh copy after the agent is done, without any key |
| Cost, tokens, turns, duration | reported by the tool (Claude Code, opencode), or tokens × your prices in `pricing.toml` |
| Review score | a reviewer model scores anonymous solutions with the task's rubric |
| Judge quality | planted defects caught, same verdict in both orders, swayed by cosmetic changes, agreement with tests, bonus given to its own family |

## Supported agents

| Adapter | Tool | Login | Cost reported |
|---|---|---|---|
| `claude-code` | Claude Code (`claude -p`) | your Claude login or `ANTHROPIC_API_KEY` | yes |
| `codex` | OpenAI Codex CLI (`codex exec`) | your ChatGPT login or `OPENAI_API_KEY` | tokens only |
| `antigravity` | Google Antigravity CLI (`agy -p`) | your Google login | tokens when given |
| `opencode` | opencode: OpenAI, Google, DeepSeek, Mistral, OpenRouter, Ollama... | the provider's key | yes, when known |
| `command` | any other CLI (Gemini CLI, aider, OpenHands...), described in TOML | yours | by regex |
| `fake` | a stand-in agent for tests and dry runs | none | fixed |

Any config can run in a container (`isolation = "docker"`) so the agent sees nothing but its workspace.

## Quick start

Python 3.11 or newer, nothing to install (standard library only), plus `git` and the agent tools you want to compare.

```bash
git clone https://github.com/Mind-alia/aibench.git && cd aibench
bin/aibench doctor                                  # which tools are installed (no model called)
bin/aibench campaign campaigns/fake.toml            # the whole pipeline with the fake agent: no model, no cost
bin/aibench run demo-invoice claude-haiku --budget-usd 1
bin/aibench calibrate demo-invoice claude-opus      # can this reviewer be trusted on this task?
bin/aibench campaign campaigns/demo.toml --dry-run  # what a real campaign would run
bin/aibench report                                  # table in the terminal, then open dashboard/index.html
```

## Concepts

- **Task**: a folder with `task.toml`, a prompt, starting code (`seed` folder or `seed_git`), and **checks**: commands
  that score the finished work (hidden tests, a judge script, a measurement tool). See [docs/TASKS.md](docs/TASKS.md).
- **Configuration**: one way of solving a task: adapter, model, effort, extra instructions, permissions, budget,
  isolation. One TOML file in `configs/`. See [docs/ADAPTERS.md](docs/ADAPTERS.md).
- **Run**: one configuration on one task. Everything is kept under `runs/<task>/<config>/<run>/`: prompt, logs, diff,
  final files, check logs, `run.json`.
- **Campaign**: tasks × configurations × repeat, with a total budget cap, then reviews. Runs go round-robin, so a cap
  cuts every configuration evenly.
- **Review**: a configuration used as reviewer reads anonymous candidates (tool traces removed) and scores them.
- **Calibration**: the reviewer compares a known-good solution with planted-defect and cosmetic variants, in both
  orders. See [docs/JUDGES.md](docs/JUDGES.md).

## Your own tasks stay private

Put private task packs outside the repository and point to them in `aibench.local.toml` (ignored by Git):

```toml
tasks_dirs = ["/path/to/my-private-tasks"]
```

Hidden tests that are published end up in training data, and a published test no longer measures anything.

## Honest limits

- One run is an anecdote. Use `repeat = 3` or more; the report flags configurations with fewer than 3 runs.
- Review scores are opinions with known biases. Hidden tests decide correctness; reviews weigh design, tests and
  robustness. Calibrate a judge on your tasks before you rely on it.
- Tools change fast. Adapters read documented output formats, but a tool update can change them: `aibench doctor`
  and the fake campaign catch the plumbing, a one-run smoke test catches the rest.

## Where it comes from

aibench follows [aiharness](https://github.com/Mind-alia/aiharness), a kit that runs coding agents through a
verification circuit. Its studies found that the best setup depended on the work: a single strong agent matched or
beat the circuit on vague requests, while the circuit was sometimes cheaper on work already cut into precise task
sheets. That is the question this bench answers: which configuration does your kind of work best, and at what cost.

Safety model: [SECURITY.md](SECURITY.md). License: MIT.
