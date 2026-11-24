# Rules for agents working on this repository

aibench benchmarks coding agents. Read `README.md` first, then the module you change.

1. **Standard library only.** No dependency in `pyproject.toml`; tests use `unittest`.
2. **Tests pass before any commit**: `PYTHONPATH=src python3 -m unittest discover -s tests -t .`. A change to an adapter
   comes with a test of its `build` and `parse` on a real output sample.
3. **No secret anywhere in the repository**, not even in a test. Keys reach agents only through `env_pass`.
4. **Never commit** `runs/`, `aibench.local.toml`, or a private task pack. Public tasks under `tasks/` are published with
   their hidden tests on purpose (demo only).
5. **An agent never sees hidden files**: nothing a check uses may be copied into the agent workspace.
6. Code, comments and docs in English; `docs/GUIDE-FR.md` is a short guide in French.
7. Only the owner pushes, publishes, makes the repository public or deletes anything. Ask; do not assume.
8. Small changes, one purpose each; update the docs in the same commit as the code they describe.
