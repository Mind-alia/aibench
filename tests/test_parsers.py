import json
import tempfile
import unittest
from pathlib import Path

from aibench.adapters import REVIEW, WORK, Context, get_adapter
from aibench.model import AgentConfig, Check
from aibench.scoring import parse_result


def config(adapter, **kwargs):
    return AgentConfig(id="c", title="c", adapter=adapter, path=Path("/tmp/c.toml"), **kwargs)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "w").mkdir()
        (root / "s").mkdir()
        self.ctx = Context(workdir=root / "w", scratch=root / "s", prompt="do it", mode=WORK, timeout_s=60)

    def tearDown(self):
        self.tmp.cleanup()


class ClaudeTest(Base):
    def test_build_work_and_review(self):
        adapter = get_adapter("claude-code")
        argv = adapter.build(config("claude-code", model="haiku", budget_usd=2), self.ctx, ["claude"]).argv
        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "2")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "acceptEdits")
        self.assertIn("WebSearch", argv[argv.index("--disallowedTools") + 1])
        self.ctx.mode = REVIEW
        argv = adapter.build(config("claude-code"), self.ctx, ["claude"]).argv
        self.assertNotIn("Edit", argv[argv.index("--allowedTools") + 1].split(","))

    def test_parse_result_with_model_usage(self):
        out = "noise\n" + json.dumps({
            "type": "result", "subtype": "success", "is_error": False, "result": "done", "total_cost_usd": 0.42,
            "num_turns": 7, "modelUsage": {"claude-haiku-5-5": {"inputTokens": 100, "outputTokens": 50,
                                                                 "cacheReadInputTokens": 1000,
                                                                 "cacheCreationInputTokens": 10}}})
        outcome = get_adapter("claude-code").parse(config("claude-code"), self.ctx, out, "", 0)
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.usage.cost_usd, 0.42)
        self.assertEqual(outcome.usage.input_tokens, 1110)
        self.assertEqual(outcome.usage.cache_read_tokens, 1000)
        self.assertEqual(outcome.final_text, "done")

    def test_parse_budget_stop_is_an_error(self):
        out = json.dumps({"type": "result", "subtype": "error_max_budget_usd", "is_error": True, "total_cost_usd": 2.0})
        outcome = get_adapter("claude-code").parse(config("claude-code"), self.ctx, out, "", 1)
        self.assertFalse(outcome.ok)
        self.assertIn("error_max_budget_usd", outcome.error)


class CodexTest(Base):
    def test_build(self):
        argv = get_adapter("codex").build(config("codex", model="m", effort="high"), self.ctx, ["codex"]).argv
        self.assertEqual(argv[:2], ["codex", "exec"])
        self.assertEqual(argv[argv.index("--sandbox") + 1], "workspace-write")
        self.assertIn("model_reasoning_effort=high", argv)
        self.assertEqual(argv[-1], "-")

    def test_parse_events(self):
        events = [{"type": "thread.started"},
                  {"type": "item.completed", "item": {"type": "agent_message", "text": "first"}},
                  {"type": "turn.completed", "usage": {"input_tokens": 500, "cached_input_tokens": 300, "output_tokens": 40}},
                  {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 10}}]
        out = "\n".join(json.dumps(e) for e in events)
        outcome = get_adapter("codex").parse(config("codex"), self.ctx, out, "", 0)
        self.assertTrue(outcome.ok)
        self.assertEqual((outcome.usage.input_tokens, outcome.usage.cache_read_tokens, outcome.usage.output_tokens),
                         (600, 300, 50))
        self.assertIsNone(outcome.usage.cost_usd)
        self.assertEqual(outcome.final_text, "first")

    def test_failed_turn(self):
        out = json.dumps({"type": "turn.failed", "error": {"message": "quota"}})
        outcome = get_adapter("codex").parse(config("codex"), self.ctx, out, "", 1)
        self.assertFalse(outcome.ok)
        self.assertIn("quota", outcome.error)


class AntigravityTest(Base):
    def test_build_allows_commands_only_when_asked(self):
        adapter = get_adapter("antigravity")
        argv = adapter.build(config("antigravity"), self.ctx, ["agy"]).argv
        self.assertNotIn("--settings", argv)
        argv = adapter.build(config("antigravity", settings={"allow_commands": ["python3"]}), self.ctx, ["agy"]).argv
        self.assertEqual(json.loads(argv[argv.index("--settings") + 1]), {"permissions": {"allow": ["command(python3)"]}})

    def test_parse_pretty_envelope_with_denials(self):
        out = "log line\n" + json.dumps({"status": "SUCCESS", "response": "ok", "denied_actions": [{"name": "RunCommand"}],
                                         "usage": {"input_tokens": 9, "output_tokens": 3}}, indent=2)
        outcome = get_adapter("antigravity").parse(config("antigravity"), self.ctx, out, "", 0)
        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.notes, ["denied: RunCommand"])
        self.assertEqual(outcome.usage.input_tokens, 9)


class OpenCodeTest(Base):
    def test_parse_steps(self):
        events = [{"type": "text", "part": {"type": "text", "text": "hello"}},
                  {"type": "step_finish", "part": {"type": "step-finish", "cost": 0.01,
                                                   "tokens": {"input": 10, "output": 5, "reasoning": 2,
                                                              "cache": {"read": 100, "write": 0}}}},
                  {"type": "step_finish", "part": {"type": "step-finish", "cost": 0.02,
                                                   "tokens": {"input": 1, "output": 1, "cache": {}}}}]
        out = "\n".join(json.dumps(e) for e in events)
        outcome = get_adapter("opencode").parse(config("opencode"), self.ctx, out, "", 0)
        self.assertAlmostEqual(outcome.usage.cost_usd, 0.03)
        self.assertEqual(outcome.usage.input_tokens, 111)
        self.assertEqual(outcome.usage.output_tokens, 8)
        self.assertEqual(outcome.final_text, "hello")


class CommandTest(Base):
    def test_template_and_regexes(self):
        cfg = config("command", model="m1", settings={
            "command": ["tool", "--model", "{model}", "--file", "{prompt_file}"],
            "cost_regex": r"Cost: \$([0-9.]+)", "output_tokens_regex": r"out=([0-9]+)"})
        argv = get_adapter("command").build(cfg, self.ctx, ["/usr/bin/tool"]).argv
        self.assertEqual(argv[:3], ["/usr/bin/tool", "--model", "m1"])
        self.assertEqual(Path(argv[4]).read_text(), "do it")
        outcome = get_adapter("command").parse(cfg, self.ctx, "Cost: $0.10\nCost: $0.25 out=77", "", 0)
        self.assertEqual(outcome.usage.cost_usd, 0.25)
        self.assertEqual(outcome.usage.output_tokens, 77)


class ReviewPromptTest(unittest.TestCase):
    def test_reviewer_without_commands_is_told_so(self):
        from aibench.model import Task
        from aibench.review import pair_prompt
        task = Task(id="t", title="t", root=Path("/tmp"), prompt="p")
        self.assertIn("run the code", pair_prompt(task, can_run=True))
        self.assertIn("cannot run any command", pair_prompt(task, can_run=False))
        self.assertFalse(get_adapter("antigravity").review_runs_commands)


class ResultFormatsTest(unittest.TestCase):
    def test_formats(self):
        work = Path(tempfile.mkdtemp())
        self.assertEqual(parse_result(Check("c", "x", result="pytest"), "3 failed, 10 passed in 1.2s", "", work)[:2], (10, 13))
        self.assertEqual(parse_result(Check("c", "x", result="unittest"), "", "Ran 8 tests\nFAILED (failures=2, errors=1)", work)[:2], (5, 8))
        check = Check("c", "x", result="json", passed_keys=["f2p.passed", "p2p.passed"], total_keys=["f2p.total", "p2p.total"])
        out = json.dumps({"f2p": {"passed": 1, "total": 1}, "p2p": {"passed": 58, "total": 59}})
        self.assertEqual(parse_result(check, out, "", work)[:2], (59, 60))
        (work / "r.xml").write_text('<testsuites><testsuite tests="5" failures="1" errors="0" skipped="1"/></testsuites>')
        self.assertEqual(parse_result(Check("c", "x", result="junit", junit="r.xml"), "", "", work)[:2], (3, 4))


if __name__ == "__main__":
    unittest.main()
