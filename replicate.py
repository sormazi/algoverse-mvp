"""
Aggregate several runs into one table with 95% bootstrap confidence intervals.

Works on output folders from llm_edits.py (results.json) and self_agent.py
(log.json + archive.json). Each folder is one run. Metrics are computed per run
first, then the bootstrap resamples RUNS (not rewrites), because rewrites inside
one run build on each other and are not independent.

Usage
  python3 replicate.py runs_r3_s1 runs_r3_s2 runs_r3_s3
  python3 replicate.py --group "rewrite loop" runs_r3_s* --group "agent" runs_ag_s*
"""
import json, os, random, sys

EVALS = ["normal", "single", "random", "transition", "presence"]


def load_run(folder):
    """Return (candidates, accepted) as lists of dicts with 'truth' and evaluator scores."""
    if os.path.exists(f"{folder}/log.json"):                 # self_agent
        log = json.load(open(f"{folder}/log.json"))
        arc = json.load(open(f"{folder}/archive.json"))
        cands = [r for r in log[1:] if "truth" in r]
        accepted = arc[1:]
    else:                                                     # llm_edits
        res = json.load(open(f"{folder}/results.json"))
        cands = [r for r in res if "truth" in r]
        accepted = [r for r in cands if r.get("accepted")]
    return cands, accepted


def run_metrics(folder):
    cands, acc = load_run(folder)
    uns = [r for r in cands if r["truth"] == "unsafe"]
    saf = [r for r in cands if r["truth"] == "safe"]
    m = {"n_rewrites": len(cands),
         "unsafe_rewrites": len(uns) / len(cands) if cands else None,
         "unsafe_accepted": (sum(a["truth"] == "unsafe" for a in acc) / len(acc)) if acc else None}
    for e in EVALS:
        m[f"{e}_catch"] = sum(r[e] for r in uns) / len(uns) if uns else None
        m[f"{e}_fa"] = sum(r[e] for r in saf) / len(saf) if saf else None
    return m


def boot_ci(vals, n=10000, seed=0):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None, None, None, 0
    mean = sum(vals) / len(vals)
    if len(vals) == 1:
        return mean, None, None, 1
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(vals, k=len(vals))) / len(vals) for _ in range(n))
    return mean, means[int(0.025 * n)], means[int(0.975 * n) - 1], len(vals)


def fmt(t):
    mean, lo, hi, k = t
    if mean is None:
        return "n/a"
    if lo is None:
        return f"{mean:.2f} (1 run)"
    return f"{mean:.2f} [{lo:.2f}, {hi:.2f}] (n={k})"


def table(groups):
    rows = ["unsafe_rewrites", "unsafe_accepted"] + [f"{e}_{k}" for e in EVALS for k in ("catch", "fa")]
    labels = {"unsafe_rewrites": "fraction of rewrites unsafe",
              "unsafe_accepted": "fraction of accepted versions unsafe"}
    for e in EVALS:
        labels[f"{e}_catch"] = f"{e}: catch on unsafe"
        labels[f"{e}_fa"] = f"{e}: false alarm on safe"
    out = ["| metric | " + " | ".join(groups) + " |", "|---|" + "---|" * len(groups)]
    per = {g: [run_metrics(f) for f in fs] for g, fs in groups.items()}
    for r in rows:
        out.append(f"| {labels[r]} | " + " | ".join(fmt(boot_ci([m[r] for m in per[g]])) for g in groups) + " |")
    return "\n".join(out), per


def main(argv):
    groups, cur = {}, "runs"
    i = 0
    while i < len(argv):
        if argv[i] == "--group":
            cur = argv[i + 1]
            i += 2
            continue
        groups.setdefault(cur, []).append(argv[i])
        i += 1
    md, per = table(groups)
    print(md)
    print("\nper-run:")
    for g, ms in per.items():
        for f, m in zip(groups[g], ms):
            print(f"  {g:>14} {f}: rewrites={m['n_rewrites']} unsafe={m['unsafe_rewrites']} "
                  f"acc_unsafe={m['unsafe_accepted']} transition={m['transition_catch']} "
                  f"random={m['random_catch']}")


if __name__ == "__main__":
    main(sys.argv[1:])
