# Choosing and checking a judge

A reviewer model turns "it passes the tests" into "it is good code". It is also the weakest link of a benchmark: judges
prefer the first or the second slot, longer answers, comments that praise the code, and sometimes their own family's
style. aibench therefore treats every judge as something to measure before trusting it.

## What the published evidence says (searched on 23 November 2026)

These are leads gathered by a web search, not results measured by aibench. Check the sources before you quote them.

- **No public head-to-head numbers exist for the newest models as code judges.** The closest studies are a few
  months old and use earlier versions.
- In a mid-2026 study grading coding-agent work, the strongest Claude model was the best single judge, the mid-size
  Claude close behind at a fraction of the cost, GPT similar, and Gemini Pro the best Gemini model
  ([Apollo Research](https://www.apolloresearch.ai/products/evaluating-llm-calibration-for-coding-agent-monitoring/)).
  The same study found a **panel of three providers** beat repeated runs of one model, because judges of one family
  make correlated mistakes.
- On CodeJudgeBench (code generation, repair and test generation pairs), Gemini 2.5 Pro led 26 judges and showed the
  least position bias; swapping the order of two answers moved accuracy by up to 14 points
  ([arXiv 2507.10535](https://arxiv.org/abs/2507.10535)).
- Judges favour verbose explanations and are moved by planted cues ("this code is correct"), by up to about 25 points
  in one study ([arXiv 2505.16222](https://arxiv.org/abs/2505.16222)).
- Self-preference is real but mostly reflects better answers; the harmful part shows where the judge is itself wrong,
  and hiding authorship reduces it ([arXiv 2504.03846](https://arxiv.org/abs/2504.03846)).
- Pairwise comparison beats a bare score, and judges do better when they can read everything and run the code.

**Recommendation.** Do not pick one judge on reputation. Shortlist the strongest model of each provider you can reach
(today: Claude Opus or Fable through Claude Code, the default Codex model, Gemini through Antigravity), calibrate
each on your tasks, and use a panel of the ones that pass, with hidden tests as the last word on correctness.

## Calibrating a judge with aibench

```bash
bin/aibench calibrate demo-invoice claude-opus --budget-usd 5
bin/aibench calibrate demo-invoice codex
bin/aibench calibrate demo-invoice antigravity-flash --timeout-min 10
bin/aibench report
```

For each variant of the task's calibration set, the judge compares it with the known-good reference twice, once in
each order. Planted defects come first, so a calibration stopped by `--budget-usd` still tests what matters most.
A reviewer whose tool cannot run commands (Antigravity, opencode) is told to judge by reading, otherwise it would stop
at its first refused command. The report shows:

| Measure | Good judge |
|---|---|
| planted defects caught | close to 100%: the reference wins against every defect |
| caught in both orders | the same, whichever candidate is shown first |
| same verdict in both orders | high; a low value means the verdict depends on position |
| swayed by cosmetic changes | low: renaming variables must not decide a winner |
| first slot wins | near 50%; far from it is a position bias |
| agreement with tests | on real runs, the run with more hidden tests passed gets the higher score |
| own-family bonus | near 0: how much more it likes its own provider's code than the other judges do |

A calibration set of four variants is small; differences of a few points mean little. Add variants to your private
tasks to measure judges on the work you care about.

## First calibration (24 November 2026, demo task, one repetition)

| Judge | Planted defects caught (both orders) | Cosmetic variant | Time per comparison | Cost |
|---|---|---|---|---|
| Claude Opus (Claude Code) | 6/6 (3/3 pairs) | tie in both orders | about 40 s | 1.59 $ for 8 comparisons |
| Gemini 3.8 Flash (Antigravity, reading only) | 6/6 (3/3 pairs) | tie in both orders | 4 to 8 min | subscription |
| Codex, default model | 5/6 (2/3 pairs) | tie in both orders | about 35 s | subscription |

Codex's one miss is instructive: it found the float bug but pinned it on the wrong candidate when the faulty copy was
shown first (letters A and B swapped in its reasoning). A panel's majority would have been right on every comparison.
Codex also found two real gaps in the reference solution (an unused float `default_vat_rate` was accepted; the prompt
did not say a blank description is refused); both were fixed the same day, with two more hidden tests.

The demo is too easy to separate the two perfect judges: subtler planted defects, and calibration sets on private
tasks, are the next step.
