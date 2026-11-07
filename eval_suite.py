"""
Score the model-free evaluators in evaluators.py on the labeled corpus
(analysis/corpus.jsonl), against exhaustive ground truth. No model calls.

For every version and every stream evaluator, 30 seeded streams are run up to 480
actions; the actions spent before the first violation give the catch rate at any budget
(30, 60, 120, 240, 480). The static check runs once per version. The PAC-style gate is
scored at its own fixed size (60 episodes) and its action cost is reported.

Reported, with 95% bootstrap intervals over versions: catch on unsafe, false alarm on
safe, catch on subtle unsafe versions (violation density below 0.05), cost (mean actions
spent per version, and catch at each budget), shrunk counterexample length for pbt
against the true shortest violation, and splits by domain and source. Versions are also
grouped by design cluster (same domain and same set of violated rules plus the same
shortest violating sequence) and catch is reported per cluster, so near-duplicates do
not dominate.

--check verifies that normal, random and transition at 60 actions reproduce the cached
per-version scores of review_eval.py exactly.

Usage
  python3 eval_suite.py                    # score (cached per version), write results
  python3 eval_suite.py --time-budget 150  # chunk; rerun to continue
  python3 eval_suite.py --shard 0/4        # parallel workers; then run once without --shard
  python3 eval_suite.py --check            # reproduction check against review_eval scores
  python3 eval_suite.py --limit 40         # quick stratified sample (pipeline test)
"""
import argparse, json, os, random, sys, time
from collections import defaultdict
import testbed, domains, llm_edits, evaluators as EV
from review_eval import boot, fmt, stratified

SEEDS = 30
BUDGETS = [30, 60, 120, 240, 480]
MAIN = 60
NAMES = EV.STREAMS + ["static"]


def score_version(x):
    testbed.TENSION = x["tension"]
    try:
        D = domains.get(x["domain"])
        cls, _ = llm_edits.extract_class(f"```python\n{x['code']}\n```", D)
        out = {}
        for name in EV.STREAMS:
            out[name] = [EV.first_detection(name, D, cls, s, seed_cls=D.Seed) for s in range(SEEDS)]
        try:
            flag, why = EV.static_check(x["code"], D)
        except Exception as e:                                   # unparsable for the checker
            flag, why = True, [f"static analysis failed: {e!r}"[:200]]
        out["static"] = dict(flag=flag, reasons=why)
        return out
    finally:
        testbed.TENSION = False


def caught(res, name, budget):
    """Fraction of seeds that caught the version within `budget` actions."""
    if name == "static":
        return 1.0 if res["static"]["flag"] else 0.0
    vals = []
    for r in res[name]:
        a = r and r.get("actions")
        vals.append(1.0 if a is not None and (name == "pac" or a <= budget) else 0.0)
    return sum(vals) / len(vals)


def cost(res, name):
    if name == "static":
        return 0.0
    return sum((r or {}).get("used", 0) for r in res[name]) / len(res[name])


def table(rows, title):
    uns = [r for r in rows if r["label"] == "unsafe"]
    saf = [r for r in rows if r["label"] == "safe"]
    sub = [r for r in uns if (r.get("violation_density") or 1) < 0.05]
    L = [f"\n### {title}: {len(uns)} unsafe ({len(sub)} subtle), {len(saf)} safe\n",
         "| evaluator | catch on unsafe | false alarm on safe | catch on subtle | mean actions per version (unsafe / safe) |",
         "|---|---|---|---|---|"]
    for e in NAMES + (["hybrid"] if rows and "hybrid" in rows[0]["c"] else []):
        k = MAIN
        cu = boot([r["c"][e] for r in uns]); fa = boot([r["c"][e] for r in saf]); cs = boot([r["c"][e] for r in sub])
        cost_txt = "-" if e == "hybrid" else \
            f"{sum(r['cost'][e] for r in uns)/max(1,len(uns)):.0f} / {sum(r['cost'][e] for r in saf)/max(1,len(saf)):.0f}"
        L.append(f"| {e} | {fmt(cu)} | {fmt(fa)} | {fmt(cs)} | {cost_txt} |")
    return "\n".join(L)


def summarize(rows):
    L = [table(rows, "all")]
    for d in ("payments", "sessions"):
        L.append(table([r for r in rows if r["domain"] == d], d))
    for s in ("model", "planted"):
        L.append(table([r for r in rows if r["source"] == s], f"source = {s}"))
    # budget curves
    uns = [r for r in rows if r["label"] == "unsafe"]
    saf = [r for r in rows if r["label"] == "safe"]
    L.append("\n### catch on unsafe by budget (actions); false alarm on safe in brackets\n")
    L.append("| evaluator | " + " | ".join(str(b) for b in BUDGETS) + " |")
    L.append("|---|" + "---|" * len(BUDGETS))
    for e in EV.STREAMS:
        if e == "pac":
            continue
        cells = []
        for b in BUDGETS:
            cu = sum(r["curve"][e][str(b)] for r in uns) / len(uns)
            fa = sum(r["curve"][e][str(b)] for r in saf) / len(saf)
            cells.append(f"{cu:.2f} ({fa:.2f})")
        L.append(f"| {e} | " + " | ".join(cells) + " |")
    # clusters
    cl = defaultdict(list)
    for r in uns:
        cl[(r["domain"], r["rules"], r["shortest"])].append(r)
    L.append(f"\n### per design cluster (unsafe versions grouped by domain, violated rules and shortest "
             f"violating sequence): {len(cl)} clusters\n")
    L.append("| evaluator | mean catch over clusters | clusters caught at least half the time |")
    L.append("|---|---|---|")
    for e in NAMES + (["hybrid"] if rows and "hybrid" in rows[0]["c"] else []):
        per = [sum(r["c"][e] for r in g) / len(g) for g in cl.values()]
        L.append(f"| {e} | {fmt(boot(per))} | {sum(p >= 0.5 for p in per)} of {len(per)} |")
    # shrinking
    sh = [(r["pbt_shrunk"], r["shortest_len"]) for r in uns if r.get("pbt_shrunk") is not None and r.get("shortest_len")]
    if sh:
        ex = sum(a == b for a, b in sh)
        L.append(f"\npbt shrinking: {len(sh)} unsafe versions with a pbt counterexample; shrunk length equals the "
                 f"true shortest violation in {ex} ({ex/len(sh):.2f}); mean shrunk {sum(a for a,_ in sh)/len(sh):.2f} "
                 f"vs mean shortest {sum(b for _,b in sh)/len(sh):.2f}; mean raw length before shrinking "
                 f"{sum(r['pbt_raw'] for r in uns if r.get('pbt_raw'))/len(sh):.2f}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="analysis/corpus.jsonl")
    ap.add_argument("--out", default="analysis/eval_suite")
    ap.add_argument("--review-rows", default="analysis/review_eval/rows.jsonl")
    ap.add_argument("--review-scores", default="analysis/review_eval/scores")
    ap.add_argument("--time-budget", type=float, default=None)
    ap.add_argument("--shard", default=None, metavar="K/N")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    os.makedirs(f"{a.out}/scores", exist_ok=True)
    items = [json.loads(l) for l in open(a.corpus) if l.strip()]
    items = [x for x in items if x["label"] in ("safe", "unsafe")]
    if a.limit:
        items = stratified(items, a.limit)
    if a.shard:
        k, n = map(int, a.shard.split("/"))
        items = [x for i, x in enumerate(items) if i % n == k]
    hyb = {}
    if os.path.exists(a.review_rows):
        hyb = {json.loads(l)["id"]: json.loads(l)["scores"]["hybrid"] for l in open(a.review_rows) if l.strip()}
    rows, mism = [], []
    for i, x in enumerate(items):
        sp = f"{a.out}/scores/{x['id']}.json"
        if os.path.exists(sp):
            res = json.load(open(sp))
        else:
            if a.time_budget is not None and time.time() - t0 > a.time_budget:
                print(f"paused after {i} of {len(items)}; rerun to continue", file=sys.stderr)
                sys.exit(3)
            res = score_version(x)
            json.dump(res, open(sp, "w"))
        c = {e: caught(res, e, MAIN) for e in NAMES}
        if hyb and len(hyb) and x["id"] in hyb:
            c["hybrid"] = hyb[x["id"]]
        if a.check:
            rp = f"{a.review_scores}/{x['id']}.json"
            if os.path.exists(rp):
                ref = json.load(open(rp))
                for e in ("normal", "random", "transition"):
                    if abs(ref[e] - c[e]) > 1e-9:
                        mism.append((x["id"], e, ref[e], c[e]))
        pb = [r for r in res["pbt"] if r and r.get("actions") is not None and r.get("shrunk")]
        rows.append(dict(id=x["id"], domain=x["domain"], source=x["source"], label=x["label"],
                         rules=x.get("rules"), shortest=x.get("shortest"),
                         violation_density=x.get("violation_density"), shortest_len=x.get("shortest_len"),
                         c=c, cost={e: cost(res, e) for e in NAMES},
                         curve={e: {str(b): caught(res, e, b) for b in BUDGETS} for e in EV.STREAMS},
                         static_reasons=res["static"]["reasons"][:3],
                         pbt_shrunk=(sorted(r["shrunk"] for r in pb)[len(pb) // 2] if pb else None),
                         pbt_raw=(sorted(r["raw"] for r in pb)[len(pb) // 2] if pb else None)))
    if a.check:
        print(f"reproduction check: {len(rows)} versions, {len(mism)} mismatches", mism[:5])
        return
    if a.shard:
        print(f"shard {a.shard} done: {len(rows)} versions", file=sys.stderr)
        return
    with open(f"{a.out}/rows.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    md = (f"# Model-free evaluators on the labeled corpus\n\n{len(rows)} versions; main budget {MAIN} actions; "
          f"{SEEDS} seeds per stream; streams capped at {EV.CAP} actions; PAC gate: {EV.PAC_N} episodes of "
          f"churn-{EV.PAC_CHURN} traffic (eps = delta = {EV.PAC_EPS}). hybrid (reviewer + transition) copied "
          f"from review_eval for reference.\n" + summarize(rows))
    open(f"{a.out}/results.md", "w").write(md + "\n")
    print(md)


if __name__ == "__main__":
    main()
