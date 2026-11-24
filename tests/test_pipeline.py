"""The whole chain with the fake agent: run, hidden tests, blind review, judge calibration, report."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from aibench.calibrate import calibrate
from aibench.project import load_bench
from aibench.report import build, write
from aibench.review import blind_review, review_runs
from aibench.runner import load_runs, run_one

REPO = Path(__file__).resolve().parent.parent


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        shutil.copytree(REPO / "tasks", root / "tasks")
        (root / "configs").mkdir()
        for name in ("fake", "fake-lazy", "fake-reviewer"):
            shutil.copy(REPO / "configs" / f"{name}.toml", root / "configs")
        (root / "aibench.toml").write_text('tasks_dirs = ["tasks"]\nconfigs_dirs = ["configs"]\nruns_dir = "runs"\n')
        os.environ.pop("AIBENCH_ROOT", None)
        cls.bench = load_bench(root)
        cls.task = cls.bench.task("demo-invoice")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_1_runs_are_scored_by_hidden_tests(self):
        good = run_one(self.bench, self.task, self.bench.config("fake"), label="t")
        lazy = run_one(self.bench, self.task, self.bench.config("fake-lazy"), label="t")
        self.assertEqual(good["status"], "ok", good["error"])
        self.assertEqual(good["primary"]["passed"], good["primary"]["total"])
        self.assertLess(lazy["primary"]["passed"], lazy["primary"]["total"])
        self.assertIn("invoice.py", good["files_changed"])
        run_dir = Path(self.bench.runs_dir, "demo-invoice", "fake", good["run_id"])
        self.assertFalse((run_dir / "workspace" / "_hidden_tests").exists(), "hidden tests must not leak into the run")
        self.assertTrue((run_dir / "diff.patch").read_text())

    def test_2_review_is_blind_and_mapped_back(self):
        runs = [r for r in load_runs(self.bench) if r["label"] == "t"]
        reviews = review_runs(self.bench, self.task, self.bench.config("fake-reviewer"), runs)
        self.assertEqual(len(reviews), 1)
        review = reviews[0]
        self.assertEqual(review["status"], "ok", review["error"])
        self.assertEqual(set(review["scores"]), {r["run_id"] for r in runs})
        prompt = Path(self.bench.reviews_dir, "demo-invoice", review["review_id"], "prompt.md").read_text()
        for run in runs:
            self.assertNotIn(run["config"], prompt)
        again = review_runs(self.bench, self.task, self.bench.config("fake-reviewer"), runs)
        self.assertEqual(again, [], "runs already scored by this reviewer are skipped")

    def test_3_review_strips_tool_traces(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp, "a"), Path(tmp, "b")
            for folder in (a, b):
                (folder / ".claude").mkdir(parents=True)
                (folder / "CLAUDE.md").write_text("made by claude")
                (folder / "x.py").write_text("print(1)\n")
            review = blind_review(self.bench, self.task, self.bench.config("fake-reviewer"), {"a": a, "b": b},
                                  mode="pair", order=["a", "b"])
            self.assertEqual(review["status"], "ok", review["error"])
            self.assertIn(review["winner"], ("a", "b", "tie"))

    def test_4_calibration_and_report(self):
        result = calibrate(self.bench, self.task, self.bench.config("fake-reviewer"))
        metrics = result["metrics"]
        self.assertEqual(metrics["calls"], 2 * len(self.task.calibration.variants))
        self.assertEqual(metrics["answered"], metrics["calls"])
        self.assertEqual(metrics["order_consistency"], 1.0)  # a rule that ignores order is perfectly consistent
        self.assertEqual(build(self.bench)["runs"], [], "fake runs stay out of the report by default")
        data = build(self.bench, include_test=True)
        report, dashboard = write(self.bench, data)
        self.assertTrue(dashboard.read_text().startswith("window.AIBENCH_DATA = "))
        saved = json.loads(report.read_text())
        rows = {s["config"]: s for s in saved["summary"]}
        self.assertEqual(rows["fake"]["rate_median"], 1.0)
        self.assertLess(rows["fake-lazy"]["rate_median"], 1.0)
        self.assertEqual(saved["best"][0]["best_quality"], "fake")
        reviewer = next(r for r in saved["reviewers"] if r["reviewer"] == "fake-reviewer")
        self.assertEqual(reviewer["calibrated_tasks"], 1)


if __name__ == "__main__":
    unittest.main()
