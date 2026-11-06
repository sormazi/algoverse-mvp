"""
Churn experiment report: groups self_agent.py runs by (churn, visibility) from
meta.json and reports, per condition, with 95% bootstrap CIs over runs:
  - fraction of rewrites unsafe
  - fraction of accepted versions unsafe
  - best agent unsafe (the cheapest version among those with the highest observed
    success, i.e. what someone reading the archive would deploy)
  - generation of the first unsafe acceptance
  - candidates where the own-work gate and the fixed-workload gate disagree
  - fraction of unsafe candidates rejected because a violation was noticed
    (disputed) while the fixed gate would have accepted them
Runs without churn fields in meta.json count as churn 0, visibility 0.
Run folders are only read. Writes analysis/churn_results.md.

Usage
  python3 churn_report.py runs_ep_agent_s* runs_churn_*
"""
import json, os, sys
from replicate import boot_ci, fmt


def run_stats(folder):
    meta = json.load(open(f"{folder}/meta.json"))
    log = json.load(open(f"{folder}/log.json"))
    arc = json.load(open(f"{folder}/archive.json"))
    cands = [r for r in log[1:] if "truth" in r]
    uns = [r for r in cands if r["truth"] == "unsafe"]
    acc = arc[1:]
    top = max(x.get("work", 1.0) for x in arc)
    best = min((x for x in arc if x.get("work", 1.0) == top), key=lambda x: x["cost"])
    first = next((r["gen"] for r in cands if r.get("accepted") and r["truth"] == "unsafe"), None)
    disagree = sum(1 for r in cands if "fixed_gate" in r and r["fixed_gate"] != r.get("gate_passed"))
    filtered = [r for r in uns if r.get("disputed") and r.get("fixed_gate") and not r.get("accepted")]
    return dict(cond=(meta.get("churn", 0.0), meta.get("visibility", 0.0)),
                unsafe=len(uns) / len(cands) if cands else None,
                acc_unsafe=sum(x["truth"] == "unsafe" for x in acc) / len(acc) if acc else None,
                best_unsafe=1.0 if best["truth"] == "unsafe" else 0.0,
                first=first, disagree=disagree, n=len(cands),
                filtered=len(filtered) / len(uns) if uns else None,
                n_acc=len(acc), n_acc_unsafe=sum(x["truth"] == "unsafe" for x in acc))


def main(folders):
    runs = [run_stats(f) for f in folders if os.path.exists(f"{f}/log.json")]
    groups = {}
    for r, f in zip(runs, [f for f in folders if os.path.exists(f"{f}/log.json")]):
        groups.setdefault(r["cond"], []).append((f, r))
    L = ["| churn p | visibility q | runs | rewrites unsafe | accepted unsafe | best agent unsafe | "
         "unsafe filtered by a dispute | first unsafe accepted (gen) | gate disagreements |",
         "|---|---|---|---|---|---|---|---|---|"]
    for (p, q) in sorted(groups):
        rs = [r for _, r in groups[(p, q)]]
        firsts = [r["first"] for r in rs]
        L.append(f"| {p:g} | {q:g} | {len(rs)} | {fmt(boot_ci([r['unsafe'] for r in rs]))} | "
                 f"{fmt(boot_ci([r['acc_unsafe'] for r in rs]))} | "
                 f"{sum(r['best_unsafe'] for r in rs):.0f} of {len(rs)} | "
                 f"{fmt(boot_ci([r['filtered'] for r in rs]))} | "
                 f"{', '.join('none' if x is None else str(x) for x in firsts)} | "
                 f"{sum(r['disagree'] for r in rs)} of {sum(r['n'] for r in rs)} |")
    L += ["", "per run:"]
    for (p, q) in sorted(groups):
        for f, r in groups[(p, q)]:
            L.append(f"- `{f}` (p={p:g}, q={q:g}): accepted {r['n_acc']} ({r['n_acc_unsafe']} unsafe), "
                     f"rewrites unsafe {r['unsafe']:.2f}, best agent {'unsafe' if r['best_unsafe'] else 'safe'}")
    out = "\n".join(L)
    print(out)
    os.makedirs("analysis", exist_ok=True)
    open("analysis/churn_results.md", "w").write(out + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
