# Writing a task

A task is a folder holding `task.toml`. The demo, `tasks/demo-invoice/`, is a complete example.

```toml
id = "my-task"                      # lowercase, digits, . _ -
title = "What it is"
description = "One sentence for the dashboard."
prompt_file = "prompt.md"           # what the agent is told
seed = "seed"                       # starting code, copied into a fresh workspace
# seed_git = { repo = "/path/or/url", ref = "branch-or-tag", depth = 1 }   # instead of seed
setup = ["uv sync --offline"]       # run in the workspace before the agent starts (no key in the environment)
timeout_minutes = 30
rubric_file = "rubric.md"           # for reviewers; a default rubric out of 40 is used otherwise
max_score = 40
tags = ["python"]

[[checks]]                          # one or more; the primary one is the headline score
name = "hidden-tests"
primary = true
files = "hidden"                    # copied into the finished work, at dest, after the agent is done
dest = "_hidden_tests"
command = "python3 -I _hidden_tests/run_hidden.py"
result = "json"                     # json | pytest | unittest | junit
timeout_seconds = 600
# image = "python:3.12-slim"        # run the check in a container, network off
# env = { DATABASE_URL = "sqlite:///tmp/x.db" }
# {task_dir} in the command is replaced by this task's folder (/task inside an image)

[calibration]                       # optional: lets you test judges on this task
reference = "calibration/reference"
variants = "calibration/variants"
```

## Result formats

| `result` | What is read |
|---|---|
| `json` | the last JSON object printed (or `json_file`) with `passed` and `total`; other keys with `passed_key` / `total_key`, dotted paths allowed, a list of keys is summed (`["f2p.passed", "p2p.passed"]`) |
| `pytest` | the `N passed`, `N failed`, `N error` summary line |
| `unittest` | `Ran N tests` and `FAILED (failures=..., errors=...)` |
| `junit` | a JUnit XML report at `junit = "path"` |

## Hidden tests that measure something

- Write them from the prompt, before reading any agent's code, and make them independent of its internal names: call
  only what the prompt promises (functions, a CLI, an HTTP route).
- Check them: the reference solution passes every test; a solution with one planted defect fails at least one.
  `tests/test_safety_and_task.py` does exactly that for the demo.
- Keep private tasks private (see the README): a published test leaks into training data.

## Calibration set

`reference/` is a known-good solution, laid over the seed. Each variant is a folder next to a TOML file of the same
name:

```toml
kind = "defect"        # a planted bug the judge must catch, or "cosmetic" (same behaviour, other surface)
description = "What is wrong; never shown to the judge."
```

Good variants are realistic: a float where money needs `Decimal`, a missing validation, rounding at the wrong level,
an edge case dropped. Their own tests should still pass, as a careless author's would.
