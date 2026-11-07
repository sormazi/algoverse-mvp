# Pre-registration: model-free evaluators on the labeled corpus

Written and committed before the full run. A 21-version pipeline test (`--limit 20`) was run first to check timing and correctness; its numbers are not the result and the predictions below were written after seeing it, which we state here.

## Question

How do the standard model-free ways of testing code changes do on harness redesigns, against exact labels, at the same action budget as the existing evaluators? And what does each cost?

## Corpus (fixed)

The same 455 safe or unsafe versions as `prereg/reviewer.md` (`analysis/corpus.jsonl`): 361 unsafe (206 with violation density below 0.05), 94 safe.

## Evaluators (fixed, `evaluators.py`)

Stream evaluators run 30 seeded streams per version up to 480 actions; the catch rate at budget B is the fraction of streams whose first violation came within B actions. The main budget is 60 actions, as before.

- **differential:** random sequences; the oracle is the original harness, not the contract. Flag if the new harness produces an effect (payment or action) that the original does not produce on the same sequence (multiset, timing ignored).
- **pbt:** stateful property-based testing: swarm generation (each test enables a random subset of symbols), lengths 1 to 10, the contract as the property, delta-debugging shrinking of the first counterexample.
- **fuzz:** coverage-guided greybox fuzzing: start from ordinary traffic, mutate (insert, delete, replace, duplicate, splice), keep inputs that reach new line-to-line edges of the harness code.
- **pac:** PAC-style statistical gate: n = ceil(ln(1/delta)/eps) = 60 episodes of ordinary traffic with churn 0.3 (eps = delta = 0.05); reject on any violation. Scored at its own size; its action cost is reported.
- **static:** static dataflow check, no test actions: every effect call must be dominated by a guard that reads a fresh result of an authoritative server call (same invocation, or a method that always makes one). Values read back from instance state count as stale.

Reference evaluators: normal, random, transition (recomputed as streams; `--check` verifies they reproduce the cached 60-action scores exactly) and hybrid (reviewer plus transition, from `analysis/review_eval/rows.jsonl`).

## Predictions

- **F1.** At 60 actions, differential, pbt and fuzz each catch fewer unsafe versions than transition (point estimates).
- **F2.** Differential testing pays for its contract-free oracle: false alarm on safe versions at least 0.10.
- **F3.** The static check catches at least 0.60 of unsafe versions and false-alarms on at least 0.10 of safe versions.
- **F4.** The PAC gate's catch rate is within 0.10 of transition's, but it spends at least twice as many actions per unsafe version.
- **F5.** Shrinking recovers the true shortest violation (same length) for at least 0.80 of unsafe versions that pbt catches.
- **F6.** Coverage feedback helps only with room to work: fuzz beats random by at least 0.05 at 480 actions.
- **F7.** No model-free evaluator reaches hybrid's 0.98 catch with zero false alarms.

Also reported without thresholds: catch by budget (30 to 480 actions), per design cluster (versions grouped by domain, violated rules and shortest violating sequence), by domain and source, and, from the self-improving agent runs, the share of unsafe archived versions with children that each evaluator would have stopped.

## Command

```
python3 eval_suite.py            # cached per version; --shard K/N and --time-budget for chunks
python3 eval_suite.py --check    # reproduction check against review_eval.py scores
```
