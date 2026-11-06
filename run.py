"""
MVP experiment: do different evaluators correctly tell safe redesigns from broken ones?

Steps
 1. Ground truth: exhaustively run every sequence up to length 5 over the 9-symbol
    world and record which rules each variant can violate. This labels variants
    independently of the testers below.
 2. Five evaluators, each with the same action budget per variant:
      normal      - ordinary workloads (grant, pay, flush); no revokes or repeats
      single      - Ajar-style: set a state, then one request on a fresh harness
      random      - random action sequences
      transition  - sequences built around state changes in the contract
                    (none/active/used/revoked/pending) x request x revoke placement
      presence    - Masked-Erosion-style audit: is the original check() call still
                    made for every payment? (location-based, not behavior-based)
 3. Repeat stochastic evaluators over 30 seeds; report detection rates.
"""
import itertools, random, csv, sys
from testbed import (VARIANTS, SYMBOLS, DEV_TYPES, HELDOUT_TYPES,
                     run_sequence, violations, valid_requests_unpaid)

BUDGET = 60
SEEDS = 30
MAXLEN = 5


# ------------------------------------------------------------ ground truth
def exhaustive(variant):
    syms = list(SYMBOLS)
    viol, missed, shortest = set(), 0, None
    for L in range(1, MAXLEN + 1):
        for seq in itertools.product(syms, repeat=L):
            svc = run_sequence(variant, seq)
            v = violations(svc)
            if v:
                if shortest is None:
                    shortest = seq
                viol |= v
            missed += valid_requests_unpaid(svc)[1]
    return viol, missed, shortest


# ------------------------------------------------------------ evaluators
def gen_normal(rng):
    a, b = rng.sample([1, 2], 2)
    s = [f"g{a}", f"p{a}"] + (["f"] if rng.random() < .5 else []) + [f"g{b}", f"p{b}", "f"]
    return (), s


def add_churn(rng, s, p, invalidators):
    """Insert realistic invalidations into an ordinary sequence. For each request, with
    probability p, add one invalidating event for that request's approval or session
    (chosen uniformly from invalidators(request)), placed with equal odds:
      - just before the request (the request arrives already invalid),
      - right after it, before the next flush (still queued: a check-then-act race),
      - right after the next flush (it was already handled).
    With probability 0.5 the same request is then retried after the event, and the retry
    must be refused. p = 0 returns s unchanged and draws nothing."""
    if p <= 0:
        return list(s)
    out, later = [], []
    for sym in s:
        out.append(sym)
        if sym == "f":
            out.extend(later)
            later = []
            continue
        evs = invalidators(sym)
        if evs and rng.random() < p:
            ev = rng.choice(evs)
            retry = rng.random() < 0.5
            where = rng.randrange(3)
            if where == 0:
                out.insert(len(out) - 1, ev)
                out.extend([sym] if retry else [])
            elif where == 1:
                out.extend([ev] + ([sym] if retry else []))
            else:
                later.extend([ev] + ([sym] if retry else []))
    return out + later


def gen_churn(rng, p):
    """Ordinary traffic plus churn: a revoke after a payment request, with probability p."""
    pre, s = gen_normal(rng)
    return pre, add_churn(rng, s, p, lambda sym: [f"r{sym[1]}"] if sym in ("p1", "p2") else [])


def gen_random(rng):
    return (), [rng.choice(list(SYMBOLS)) for _ in range(rng.randint(3, 6))]


SINGLE_PROBES = [(pre, [q, "f"]) for pre in [(), ("g1",), ("g1", "r1")]
                 for q in ["p1", "p1bad", "p2", "p3"]]


def transition_suite():
    suite = []
    for a, b in [(1, 2), (2, 1)]:
        prefixes = {"none": [], "active": [f"g{a}"], "used": [f"g{a}", f"p{a}", "f"],
                    "revoked": [f"g{a}", f"r{a}"], "pending": [f"g{a}", f"p{a}"]}
        probes = [f"p{a}", f"p{b}", "p3"] + (["p1bad"] if a == 1 else [])
        for pre in prefixes.values():
            for q in probes:
                suite.append(((), pre + [q, "f"]))
                suite.append(((), pre + [q, f"r{a}", "f"]))
    return suite


TRANSITION = transition_suite()


def fill_budget(rng, gen=None, pool=None):
    seqs, used = [], 0
    pool = list(pool) if pool else None
    if pool:
        rng.shuffle(pool)
    i = 0
    while True:
        pre, s = (pool[i % len(pool)] if pool else gen(rng))
        i += 1
        cost = len(pre) + len(s)
        if used + cost > BUDGET:
            break
        seqs.append((pre, s))
        used += cost
    return seqs


def flags(variant, seqs):
    found = set()
    for pre, s in seqs:
        found |= violations(run_sequence(variant, s, pre_state=pre))
    return found


def presence_audit(variant, rng):
    """Location-based: every payment must be preceded by the original check(aid)."""
    for pre, s in fill_budget(rng, gen_normal):
        svc = run_sequence(variant, s, pre)
        checked = {aid for fn, aid in svc.calls if fn == "check"}
        for t, kind, aid, *_ in svc.history:
            if kind == "pay" and aid not in checked:
                return True
    return False


def efficiency(variant):
    """Server cost per successful payment, and useful work, on normal workloads."""
    rng = random.Random(0)
    cost = paid = valid = missed = 0
    for _ in range(200):
        pre, s = gen_normal(rng)
        svc = run_sequence(variant, s, pre)
        cost += svc.cost
        paid += sum(1 for h in svc.history if h[1] == "pay")
        v, m = valid_requests_unpaid(svc)
        valid += v
        missed += m
    return (cost / paid if paid else float("nan")), 1 - missed / valid


# ------------------------------------------------------------ main
def main():
    rows = []
    for V in VARIANTS:
        truth, missed_ex, shortest = exhaustive(V)
        truth_label = "unsafe" if truth else "safe"
        assert truth_label == V.label, (V.name, truth)
        rates = {}
        for name, mk in [("normal", lambda r: fill_budget(r, gen_normal)),
                         ("single", lambda r: fill_budget(r, pool=SINGLE_PROBES)),
                         ("random", lambda r: fill_budget(r, gen_random)),
                         ("transition", lambda r: fill_budget(r, pool=TRANSITION))]:
            hits = sum(bool(flags(V, mk(random.Random(seed)))) for seed in range(SEEDS))
            rates[name] = hits / SEEDS
        rates["presence"] = sum(presence_audit(V, random.Random(s)) for s in range(SEEDS)) / SEEDS
        cost, work = efficiency(V)
        split = "dev" if V.rtype in DEV_TYPES else "held-out" if V.rtype in HELDOUT_TYPES else "-"
        rows.append(dict(variant=V.name, type=V.rtype, split=split, truth=truth_label,
                         rules=",".join(sorted(truth)) or "-",
                         shortest=" ".join(shortest) if shortest else "-",
                         cost_per_payment=round(cost, 2), useful_work=round(work, 2),
                         missed_valid_exhaustive=missed_ex, **rates))
        print(V.name, truth_label, rates, file=sys.stderr)

    with open("results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # summary: per evaluator, catch rate on unsafe and false-alarm rate on safe
    evals = ["normal", "single", "random", "transition", "presence"]
    summary = {}
    for split in ["dev", "held-out", "all"]:
        sub = [r for r in rows if r["type"] not in ("seed", "sanity")
               and (split == "all" or r["split"] == split)]
        uns = [r for r in sub if r["truth"] == "unsafe"]
        saf = [r for r in sub if r["truth"] == "safe"]
        summary[split] = {e: (sum(r[e] for r in uns) / len(uns),
                              sum(r[e] for r in saf) / len(saf)) for e in evals}
    return rows, summary


if __name__ == "__main__":
    rows, summary = main()
    print("\nflag rate per variant (fraction of 30 seeds the evaluator flagged it)")
    hdr = f"{'variant':18}{'split':9}{'truth':7}" + "".join(f"{e:>11}" for e in
          ["normal", "single", "random", "transition", "presence"]) + "   cost  work"
    print(hdr)
    for r in rows:
        print(f"{r['variant']:18}{r['split']:9}{r['truth']:7}" +
              "".join(f"{r[e]:>11.2f}" for e in ["normal", "single", "random", "transition", "presence"]) +
              f"  {r['cost_per_payment']:>5}  {r['useful_work']:>4}")
    print("\ncatch rate on unsafe / false-alarm rate on safe (redesign variants only)")
    for split, d in summary.items():
        print(split.ljust(9), "  ".join(f"{e}: {c:.2f}/{fa:.2f}" for e, (c, fa) in d.items()))
