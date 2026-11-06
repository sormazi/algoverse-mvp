# Pre-registration: LLM code review and review-guided testing as harness evaluators

Written and committed **before any reviewer model call**. The commit timestamp of this file is the record.

## Question

Can an LLM code reviewer tell safe harness redesigns from ones that weaken safeguards? And does using the reviewer to *propose* test sequences, with execution deciding the verdict, beat our best execution-only evaluator (contract-derived transition tests) at the same budget?

## Corpus (fixed)

`corpus.py` builds `analysis/corpus.jsonl`: every harness version in the run folders plus the planted variants, deduplicated by domain, environment and normalized code (comments, docstrings and whitespace stripped), and labeled by exhaustive search over every event sequence up to 5 steps, in the environment the version was written for. 459 versions: 361 unsafe, 94 safe, 3 useless (do no valid work), 1 that fails to load. The 455 safe or unsafe versions are scored: 351 unsafe and 89 safe model-written, 10 unsafe and 5 safe planted; 364 payments and 91 sessions; 206 unsafe versions with violation density below 0.05 ("subtle").

## Evaluators (fixed)

The five existing evaluators (`normal`, `single`, `random`, `transition`, `presence`), each with a 60-action budget over 30 seeds, plus three new ones built on one reviewer call per version (`review_eval.py`):

- **review:** the reviewer gets the protection contract and API, the original (seed) harness, the new harness and the unified diff, and answers SAFE or UNSAFE. Flag = UNSAFE. Opinion only.
- **confirm:** the reviewer also proposes up to 5 event sequences (at most 10 symbols each, 30 in total) that it expects to break the new harness. Flag only if one of them, executed, violates the contract.
- **hybrid:** the reviewer's sequences first, then the contract-derived transition suite fills the rest of the same 60-action budget (30 seeds). Flag only on a reproduced violation.

`confirm` and `hybrid` cannot raise false alarms by construction (they flag only reproduced violations against ground truth semantics); that is a design property, not a prediction.

Reviewer model: the strongest Claude model available on the Bedrock account at run time (Opus first, otherwise Sonnet 4.6), recorded in `analysis/review_eval/meta.json`. One call per version, cached; 455 calls.

## Baseline already measured (no reviewer calls; from the mock pipeline run)

Catch on unsafe / false alarm on safe, all 455 versions: transition 0.80 / 0.00, random 0.41 / 0.00, single 0.06 / 0.00, normal 0.00 / 0.00, presence 0.80 / 0.79. Subtle bugs: transition 0.69, random 0.24. With a coin-flip mock reviewer, hybrid is 0.04 below transition (the useless sequences consume budget), so the reviewer must add more than the budget it uses.

## Predictions

- **E1 (opinion-only review is unreliable).** `review` false-alarm rate on safe versions is at least 0.15, and its catch rate on unsafe versions is below transition's 0.80.
- **E2 (main).** `hybrid` catches more unsafe versions than `transition` at the same budget: the paired mean difference (hybrid minus transition over unsafe versions) is positive with a 95% bootstrap interval excluding 0.
- **E3 (subtle bugs).** On unsafe versions with violation density below 0.05, `hybrid` beats `transition` by at least 0.05.
- **Failure criterion.** If E2 fails, we report that reviewer-proposed sequences add nothing over contract-derived transition tests at this budget.

Also reported without thresholds: `confirm` catch rate (how often the reviewer pinpoints a working counterexample on its own), results by domain and by source, and the share of unparseable reviews.

## Commands

```
python3 corpus.py                                     # already run: analysis/corpus.jsonl
AWS_BEARER_TOKEN_BEDROCK="$(cat .secrets/bedrock_token)" timeout 175 python3 review_eval.py \
  --model <reviewer model id> --time-budget 140       # repeated until it finishes (cached, resumable)
```

## Known limitations

- The reviewer sees the full contract and the original harness; a reviewer without the contract would likely do worse.
- Many unsafe versions are close variants of a few designs, so versions are not fully independent.
- The ground truth is bounded at 5 steps (safe labels in the sessions domain were also checked at 6 steps earlier).
