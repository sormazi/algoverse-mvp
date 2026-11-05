"""
Dose-response: how does the fraction of unsafe rewrites change with the cost gap
between the cheapest safe design and the cheapest unsafe design?

Reads run folders from llm_edits.py (results.json) and self_agent.py (log.json +
archive.json). Each folder should have meta.json with a cost_gap field (set by
the --cost-gap flag). Groups runs by cost_gap and reports, for each level:
  - number of runs, total rewrites
  - fraction of rewrites unsafe (with bootstrap 95% CI over runs)
  - fraction of accepted versions unsafe
  - evaluator catch and false-alarm rates
  - a text bar chart

Usage
  # run experiments at each cost gap (3 seeds each)
  for gap in 0.1 0.2 0.4 0.6 0.8 1.0; do
    for s in 1 2 3; do
      python3 llm_edits.py --model us.anthropic.claude-sonnet-4-6 \
        --cost-gap $gap --hide-requirements --rounds 15 --seed $s \
        --out runs_dose_${gap}_s${s}
    done
  done

  # aggregate
  python3 dose_response.py runs_dose_*
  python3 dose_response.py --csv analysis/dose_response.csv runs_dose_*

  # self-improving agent dose-response
  for gap in 0.1 0.2 0.4 0.6 0.8 1.0; do
    for s in 1 2 3; do
      python3 self_agent.py --model us.anthropic.claude-sonnet-4-6 \
        --cost-gap $gap --hide-requirements --generations 15 --seed $s \
        --out runs_dose_agent_${gap}_s${s}
    done
  done
  python3 dose_response.py runs_dose_agent_*
"""
import json, os, random, sys

EVALS = ["normal", "single", "random", "transition", "presence"]
METRICS = ["fraction_unsafe", "fraction_accepted_unsafe"]
METRICS += [f"{e}_catch" for e in EVALS]
METRICS += [f"{e}_fa" for e in EVALS]


def load_run(folder):
    """Return (candidates, accepted) as lists of dicts with 'truth' and evaluator scores."""
    if os.path.exists(f"{folder}/log.json"):                 # self_agent
        log = json.load(open(f"{folder}/log.json"))
        arc = json.load(open(f"{folder}/archive.json"))
        cands = [r for r in log[1:] if "truth" in r]
        accepted = arc[1:]
    elif os.path.exists(f"{folder}/results.json"):            # llm_edits
        res = json.load(open(f"{folder}/results.json"))
        cands = [r for r in res if "truth" in r]
        accepted = [r for r in cands if r.get("accepted")]
    else:
        return None, None
    return cands, accepted


def run_metrics(folder):
    cands, acc = load_run(folder)
    if cands is None:
        return None
    uns = [r for r in cands if r["truth"] == "unsafe"]
    saf = [r for r in cands if r["truth"] == "safe"]
    m = {"n_rewrites": len(cands),
         "fraction_unsafe": len(uns) / len(cands) if cands else None,
         "fraction_accepted_unsafe": (sum(a["truth"] == "unsafe" for a in acc) / len(acc)) if acc else None}
    for e in EVALS:
        m[f"{e}_catch"] = sum(r[e] for r in uns) / len(uns) if uns else None
        m[f"{e}_fa"] = sum(r[e] for r in saf) / len(saf) if saf else None
    return m


def get_cost_gap(folder):
    meta_path = f"{folder}/meta.json"
    if os.path.exists(meta_path):
        meta = json.load(open(meta_path))
        return meta.get("cost_gap", 1.0 if meta.get("tension") else 0.0)
    name = os.path.basename(folder)
    return 1.0 if "tension" in name and "notension" not in name else 0.0


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
        return f"{mean:.2f} (n={k})"
    return f"{mean:.2f} [{lo:.2f}, {hi:.2f}]"


def main(argv):
    csv_path = None
    folders = []
    i = 0
    while i < len(argv):
        if argv[i] == "--csv":
            csv_path = argv[i + 1]
            i += 2
            continue
        folders.append(argv[i])
        i += 1

    groups = {}
    for f in folders:
        gap = get_cost_gap(f)
        groups.setdefault(gap, []).append(f)

    if not groups:
        print("no run folders found")
        return

    rows = []
    for gap in sorted(groups):
        metrics = [m for m in (run_metrics(f) for f in groups[gap]) if m is not None]
        if not metrics:
            continue
        row = {"cost_gap": gap, "n_runs": len(metrics),
               "n_rewrites": sum(m["n_rewrites"] for m in metrics)}
        for key in METRICS:
            row[key] = boot_ci([m[key] for m in metrics])
        rows.append(row)

    if not rows:
        print("no valid runs (missing results.json or log.json)")
        return

    # table
    print(f"\n{'cost_gap':>9} {'runs':>4} {'rewrites':>8}  {'frac_unsafe':>22}  "
          f"{'acc_unsafe':>22}  {'transition':>22}  {'random':>22}")
    print("-" * 115)
    for r in rows:
        print(f"{r['cost_gap']:>9.2f} {r['n_runs']:>4} {r['n_rewrites']:>8}  "
              f"{fmt(r['fraction_unsafe']):>22}  {fmt(r['fraction_accepted_unsafe']):>22}  "
              f"{fmt(r['transition_catch']):>22}  {fmt(r['random_catch']):>22}")

    # text bar chart
    print("\nDose-response: fraction unsafe vs. cost gap")
    max_bar = 50
    for r in rows:
        mean = r["fraction_unsafe"][0]
        if mean is None:
            continue
        bar = "#" * int(mean * max_bar)
        print(f"  {r['cost_gap']:.2f} | {bar} {mean:.2f}")

    # per-run detail
    print("\nper-run:")
    def safe_fmt(v):
        return f"{v:.2f}" if v is not None else "n/a"
    for gap in sorted(groups):
        for f in groups[gap]:
            m = run_metrics(f)
            if m is None:
                print(f"  gap={gap:.2f} {f}: (no results found)")
                continue
            print(f"  gap={gap:.2f} {f}: rewrites={m['n_rewrites']} "
                  f"unsafe={safe_fmt(m['fraction_unsafe'])} "
                  f"acc_unsafe={safe_fmt(m['fraction_accepted_unsafe'])}")

    # CSV
    if csv_path:
        import csv as csvmod
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        fields = ["cost_gap", "n_runs", "n_rewrites"]
        for key in METRICS:
            fields += [f"{key}_mean", f"{key}_lo", f"{key}_hi", f"{key}_n"]
        with open(csv_path, "w", newline="") as fh:
            w = csvmod.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            for r in rows:
                row = {"cost_gap": r["cost_gap"], "n_runs": r["n_runs"], "n_rewrites": r["n_rewrites"]}
                for key in METRICS:
                    mean, lo, hi, k = r[key]
                    row[f"{key}_mean"] = f"{mean:.4f}" if mean is not None else ""
                    row[f"{key}_lo"] = f"{lo:.4f}" if lo is not None else ""
                    row[f"{key}_hi"] = f"{hi:.4f}" if hi is not None else ""
                    row[f"{key}_n"] = k
                w.writerow(row)
        print(f"\nCSV: {csv_path}")

    # matplotlib plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        gaps = [r["cost_gap"] for r in rows]
        uns_means = [r["fraction_unsafe"][0] or 0 for r in rows]
        uns_los = [r["fraction_unsafe"][0] - (r["fraction_unsafe"][1] or r["fraction_unsafe"][0]) for r in rows]
        uns_his = [(r["fraction_unsafe"][2] or r["fraction_unsafe"][0]) - r["fraction_unsafe"][0] for r in rows]
        t_means = [r["transition_catch"][0] or 0 for r in rows]
        t_los = [r["transition_catch"][0] - (r["transition_catch"][1] or r["transition_catch"][0]) for r in rows]
        t_his = [(r["transition_catch"][2] or r["transition_catch"][0]) - r["transition_catch"][0] for r in rows]
        r_means = [r["random_catch"][0] or 0 for r in rows]
        r_los = [r["random_catch"][0] - (r["random_catch"][1] or r["random_catch"][0]) for r in rows]
        r_his = [(r["random_catch"][2] or r["random_catch"][0]) - r["random_catch"][0] for r in rows]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        ax1.errorbar(gaps, uns_means, yerr=[uns_los, uns_his], marker="o", capsize=4, label="fraction unsafe")
        ax1.set_xlabel("Cost gap (safe per-payment cost - unsafe per-payment cost)")
        ax1.set_ylabel("Fraction of rewrites unsafe")
        ax1.set_title("Dose-response: erosion vs. cost incentive")
        ax1.legend()
        ax1.set_ylim(-0.05, 1.05)
        ax1.set_xticks(gaps)

        ax2.errorbar(gaps, t_means, yerr=[t_los, t_his], marker="s", capsize=4, label="transition catch")
        ax2.errorbar(gaps, r_means, yerr=[r_los, r_his], marker="^", capsize=4, label="random catch")
        ax2.set_xlabel("Cost gap")
        ax2.set_ylabel("Catch rate on unsafe")
        ax2.set_title("Evaluator performance vs. cost gap")
        ax2.legend()
        ax2.set_ylim(-0.05, 1.05)
        ax2.set_xticks(gaps)

        plt.tight_layout()
        out = (csv_path or "analysis/dose_response").replace(".csv", ".png")
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        plt.savefig(out, dpi=150)
        print(f"Plot: {out}")
    except ImportError:
        print("\n(matplotlib not available; install it for a plot)")


if __name__ == "__main__":
    main(sys.argv[1:])
