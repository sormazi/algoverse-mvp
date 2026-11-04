"""Budget sweep: catch rate on unsafe variants per evaluator as the action budget grows."""
import random, run
from testbed import VARIANTS, DEV_TYPES, HELDOUT_TYPES
gens = {"normal": lambda r: run.fill_budget(r, run.gen_normal),
        "single": lambda r: run.fill_budget(r, pool=run.SINGLE_PROBES),
        "random": lambda r: run.fill_budget(r, run.gen_random),
        "transition": lambda r: run.fill_budget(r, pool=run.TRANSITION)}
print("budget split     " + "".join(f"{k:>12}" for k in gens))
for B in [20, 40, 60, 120, 240, 480]:
    run.BUDGET = B
    for split, types in [("dev", DEV_TYPES), ("held-out", HELDOUT_TYPES)]:
        uns = [V for V in VARIANTS if V.rtype in types and V.label == "unsafe"]
        out = []
        for name, g in gens.items():
            hits = [bool(run.flags(V, g(random.Random(s)))) for V in uns for s in range(30)]
            out.append(sum(hits) / len(hits))
        print(f"{B:<7}{split:10}" + "".join(f"{x:>12.2f}" for x in out))
