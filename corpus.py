"""
Benchmark corpus for harness evaluators.

Collects every harness version in the run folders (model-written) plus the planted
variants (hand-written), removes duplicates (same domain, same environment, same code
after stripping comments, docstrings and whitespace), and labels each one by exhaustive
search in the environment it was written for (payments with or without tension mode,
or sessions). Writes analysis/corpus.jsonl, one version per line:

  id, domain, tension, source ("model" or "planted"), origin (first file seen),
  n_copies, code, label ("safe", "unsafe" or "useless"), rules, shortest (sequence),
  shortest_len, violation_density

Resumable: versions already in the output are skipped, so it can run in short chunks
(--time-budget SECONDS). Run folders are only read.

Usage
  python3 corpus.py                      # build or extend analysis/corpus.jsonl
  python3 corpus.py --time-budget 150    # stop cleanly after ~150 s; rerun to continue
"""
import argparse, glob, hashlib, inspect, json, os, re, sys, time
import testbed, sessions, domains, llm_edits

OUT = "analysis/corpus.jsonl"


def norm(code):
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    code = re.sub(r"'''[\s\S]*?'''", "", code)
    code = re.sub(r"#[^\n]*", "", code)
    return re.sub(r"\s+", " ", code).strip()


def vid(domain, tension, code):
    return hashlib.sha1(f"{domain}|{tension}|{norm(code)}".encode()).hexdigest()[:12]


def planted_source(cls):
    src = "\n\n".join(inspect.getsource(c) for c in reversed(cls.__mro__[:-2]))
    return src.replace(f"class {cls.__name__}(", "class Candidate(")


def collect():
    items = {}
    for d in sorted(glob.glob("runs_*")):
        if not os.path.isdir(d) or d == "runs_churn_throttled":
            continue
        meta = json.load(open(f"{d}/meta.json")) if os.path.exists(f"{d}/meta.json") else {}
        tension = bool(meta.get("tension", "tension" in d and "notension" not in d))
        dom = meta.get("domain", "payments")
        files = sorted(glob.glob(f"{d}/round_*.py")) + \
            sorted(f for f in glob.glob(f"{d}/archive/*.py") if not f.endswith("v00.py"))
        for f in files:
            code = open(f).read()
            k = vid(dom, tension, code)
            if k in items:
                items[k]["n_copies"] += 1
            else:
                items[k] = dict(id=k, domain=dom, tension=tension, source="model", origin=f, n_copies=1, code=code)
    planted = [("payments", False, V) for V in testbed.VARIANTS if V.rtype not in ("seed", "sanity")] + \
              [("sessions", False, V) for V in sessions.VARIANTS if V.rtype not in ("seed", "sanity")]
    for dom, tension, V in planted:
        code = planted_source(V)
        k = vid(dom, tension, code)
        items.setdefault(k, dict(id=k, domain=dom, tension=tension, source="planted",
                                 origin=f"{dom}:{V.name}", n_copies=1, code=code))
    return list(items.values())


def label(item):
    testbed.TENSION = item["tension"]
    D = domains.get(item["domain"])
    cls, _ = llm_edits.extract_class(f"```python\n{item['code']}\n```", D)
    viol, missed, shortest = D.exhaustive(cls)
    sub = domains.subtlety(D, cls) if viol else dict(shortest_len=None, violation_density=0.0)
    testbed.TENSION = False
    return dict(label="unsafe" if viol else ("useless" if missed else "safe"),
                rules=",".join(sorted(viol)) or "-", shortest=" ".join(shortest) if shortest else "-", **sub)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-budget", type=float, default=None)
    a = ap.parse_args()
    t0 = time.time()
    os.makedirs("analysis", exist_ok=True)
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)["id"] for l in open(OUT) if l.strip()}
    items = [x for x in collect() if x["id"] not in done]
    print(f"{len(done)} already labeled, {len(items)} to go", file=sys.stderr)
    with open(OUT, "a") as fh:
        for x in items:
            if a.time_budget is not None and time.time() - t0 > a.time_budget:
                print("paused; rerun to continue", file=sys.stderr)
                sys.exit(3)
            try:
                x.update(label(x))
            except Exception as e:
                x.update(label="error", error=repr(e)[:200])
            fh.write(json.dumps(x) + "\n")
            fh.flush()
    rows = [json.loads(l) for l in open(OUT) if l.strip()]
    from collections import Counter
    print(f"{len(rows)} versions:", dict(Counter((r["source"], r["domain"], r["label"]) for r in rows)))


if __name__ == "__main__":
    main()
