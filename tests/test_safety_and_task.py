import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aibench.model import load_config
from aibench.project import load_bench
from aibench.safety import agent_env, check_env, redact, secret_values
from aibench.scoring import run_check
from aibench.util import BenchError

REPO = Path(__file__).resolve().parent.parent


class SafetyTest(unittest.TestCase):
    def test_only_listed_secrets_reach_the_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "c.toml")
            path.write_text('adapter = "fake"\nenv_pass = ["MY_PROVIDER_KEY"]\n')
            cfg = load_config(path)
        fake_env = {"PATH": "/bin", "HOME": "/h", "MY_PROVIDER_KEY": "sk-0123456789", "OTHER_SECRET": "nope-nope-nope"}  # gitleaks:allow
        with mock.patch.dict(os.environ, fake_env, clear=True):
            env = agent_env(cfg)
            self.assertEqual(env["MY_PROVIDER_KEY"], "sk-0123456789")
            self.assertNotIn("OTHER_SECRET", env)
            self.assertNotIn("MY_PROVIDER_KEY", check_env())
            self.assertEqual(redact("key=sk-0123456789", secret_values(cfg)), "key=[REDACTED]")  # gitleaks:allow

    def test_secret_value_in_config_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "c.toml")
            path.write_text('adapter = "fake"\n[env]\nOPENAI_API_KEY = "sk-x"\n')
            with self.assertRaises(BenchError):
                load_config(path)


class DemoTaskTest(unittest.TestCase):
    """The demo task's hidden tests separate its reference from each planted defect, and ignore cosmetics."""

    def score(self, overlay: Path) -> tuple[int, int]:
        bench = load_bench(REPO)
        task = bench.task("demo-invoice")
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp, "w")
            shutil.copytree(task.seed, work)
            shutil.copytree(overlay, work, dirs_exist_ok=True)
            result = run_check(task, task.primary_check, work, Path(tmp, "out"))
        return result["passed"], result["total"]

    def test_reference_and_variants(self):
        task = load_bench(REPO).task("demo-invoice")
        passed, total = self.score(task.calibration.reference)
        self.assertEqual(passed, total)
        self.assertGreater(total, 40)
        for name, kind, _description, folder in task.calibration.variants:
            passed, total = self.score(folder)
            if kind == "defect":
                self.assertLess(passed, total, name)
            else:
                self.assertEqual(passed, total, name)


if __name__ == "__main__":
    unittest.main()
