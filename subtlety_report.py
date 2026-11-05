"""
How subtle are the unsafe versions? (Madhur's question: are we only measuring
blunt shortcuts?) Reads the candidate code saved in existing run folders, re-labels
each one exhaustively, and reports, for unsafe ones, the shortest violating
sequence length and the fraction of all sequences (up to MAXLEN) that violate.
Joins with the evaluator scores already stored in the run. No model calls; old
run folders are only read. Output: analysis/subtlety.csv plus a printed summary.

Usage
  python3 subtlety_report.py runs_tension runs_r3_s* runs_agent_s* runs_agent_tension
"""
import csv, glob, json, os, sys
import testbed, domains, llm_edits


def run_info(folder):
    meta = json.load(open(f"{folder}/meta.json")) if os.path.exists(f"{folder}/meta.json") else {}
    tension = meta.get("tension", "tension" in os.path.basename(folder) and "notension" not in folder)
    domain = meta.get("domain", "payments")
    if os.path.exists(f"{folder}/log.json"):
        recs = {r["ver"]: r for r in json.load(open(f"{folder}/log.json")) if "ver" in r}
        files = sorted(glob.glob(f"{folder}/archive/*.py"))
        key = lambda f: os.path.basename(f)[:-3]
    else:
        res = json.load(open(f"{folder}/results.json"))
        recs = {f"round_{r['round']:02d}": r for r in res}
        files = sorted(glob.glob(f"{folder}/round_*.py"))
        key = lambda f: os.path.basename(f)[:-3]
    return tension, domain, recs, files, key


def main(folders):
    rows = []
    for folder in folders:
        tension, domain, recs, files, key = run_info(folder)
        testbed.TENSION = tension
        D = domains.get(domain)
        for f in files:
            k = key(f)
            if k == "v00":
                continue
            try:
                cls, _ = llm_edits.extract_class(f"```python\n{open(f).read()}\n```", D)
                viol, _, shortest = D.exhaustive(cls)
            except Exception as e:
                print(f"skip {f}: {e!r}"[:120], file=sys.stderr)
                continue
            if not viol:
                continue
            sub = domains.subtlety(D, cls)
            r = recs.get(k, {})
            rows.append(dict(run=folder, version=k, rules=",".join(sorted(viol)),
                             shortest=" ".join(shortest), **sub,
                             accepted=r.get("accepted", k.startswith("v")),
                             **{e: r.get(e) for e in ("normal", "single", "random", "transition", "presence")}))
    testbed.TENSION = False
    os.makedirs("analysis", exist_ok=True)
    if rows:
        with open("analysis/subtlety.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"{len(rows)} unsafe versions across {len(folders)} runs\n")
    lens = {}
    for r in rows:
        lens.setdefault(r["shortest_len"], []).append(r)
    print("shortest violation length -> count, mean violation density, mean transition / random catch")
    for L in sorted(lens):
        g = [r for r in lens[L] if r["transition"] is not None]
        mean = lambda k: sum(r[k] for r in g) / len(g) if g else float("nan")
        print(f"  {L}: {len(lens[L]):3d}  density {sum(r['violation_density'] for r in lens[L]) / len(lens[L]):.4f}"
              f"  transition {mean('transition'):.2f}  random {mean('random'):.2f}")
    for lo, hi in [(0, 0.01), (0.01, 0.05), (0.05, 1)]:
        g = [r for r in rows if lo <= r["violation_density"] < hi and r["transition"] is not None]
        if g:
            print(f"density [{lo}, {hi}): n={len(g)}  transition {sum(r['transition'] for r in g) / len(g):.2f}"
                  f"  random {sum(r['random'] for r in g) / len(g):.2f}")


if __name__ == "__main__":
    main(sys.argv[1:])
