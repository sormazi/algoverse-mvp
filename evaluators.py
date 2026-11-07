"""
Model-free harness evaluators (no model calls), usable on any domain in domains.py.

Every behavioral evaluator is a *stream*: it produces one event sequence after another
and stops at the first sequence that violates the contract (or at the action cap). The
number of actions spent before the first violation gives the catch rate at every budget
from one run: a version is caught at budget B if its first violation came within B
actions. Actions are counted as in run.fill_budget (symbols in the sequence; the
automatic final flush is free), so `random`, `normal` and `transition` reproduce the
existing 60-action numbers exactly.

  normal        ordinary traffic (the existing evaluator, as a stream)
  random        uniform random sequences of 3 to 6 symbols (existing, as a stream)
  transition    the contract-derived transition suite, shuffled and cycled (existing)
  differential  random sequences; the oracle is the original harness, not the contract:
                flag if the new harness produces an effect (payment / action) that the
                original does not produce on the same sequence (multiset comparison,
                timing ignored)
  pbt           stateful property-based testing: swarm generation (each test enables a
                random subset of symbols) with lengths 1 to 10, contract invariants as the
                property, and delta-debugging shrinking of the first counterexample
  fuzz          coverage-guided greybox fuzzing: start from ordinary traffic, mutate
                (insert, delete, replace, duplicate, splice), keep inputs that reach new
                line-to-line edges of the harness code
  pac           PAC-style statistical acceptance gate: n = ceil(ln(1/delta)/eps) episodes
                of realistic traffic with churn (eps = delta = 0.05, so 60 episodes, churn
                0.3); reject on any violation. Bounds the violation rate on that traffic,
                not the worst case
  static        static dataflow check, zero test actions: every effect call must be
                dominated by a guard that reads a fresh result of an authoritative server
                call (made in the same invocation, or returned by a method that always makes
                one); values read back from instance state count as stale
"""
import ast, inspect, itertools, math, random, sys, textwrap

CAP = 480                     # action cap per stream
PAC_EPS, PAC_DELTA, PAC_CHURN = 0.05, 0.05, 0.3
PAC_N = math.ceil(math.log(1 / PAC_DELTA) / PAC_EPS)          # 60 episodes

STREAMS = ["normal", "random", "transition", "differential", "pbt", "fuzz", "pac"]

AUTH = {"payments": {"check", "check_batch", "check_and_consume", "consume", "version"},
        "sessions": {"introspect", "introspect_batch"}}
EFFECT = "execute"


# ------------------------------------------------------------------ helpers
def effects(D, svc):
    if D.name == "payments":
        return [h[2:5] for h in svc.history if h[1] == "pay"]
    return [(h[3], h[4]) for h in svc.history if h[2] == "exec"]


def _bad(D, cls, s, pre=()):
    return bool(D.violations(D.run_sequence(cls, s, pre)))


def shrink(D, cls, s):
    """Delta debugging (ddmin-style): remove chunks, then single symbols, while the
    sequence still violates the contract."""
    s = list(s)
    n = 2
    while len(s) >= 2:
        chunk = max(1, len(s) // n)
        reduced = False
        for i in range(0, len(s), chunk):
            cand = s[:i] + s[i + chunk:]
            if cand and _bad(D, cls, cand):
                s, n, reduced = cand, max(n - 1, 2), True
                break
        if not reduced:
            if chunk == 1:
                break
            n = min(len(s), n * 2)
    return s


# ------------------------------------------------------------------ generators
def gen_stream(name, D, cls, rng):
    """Yield (pre, seq, extra) forever; extra may carry a flag for oracle-based streams."""
    if name == "normal":
        while True:
            yield D.gen_normal(rng)
    elif name == "random" or name == "differential":
        while True:
            yield D.gen_random(rng)
    elif name == "transition":
        pool = list(D.TRANSITION)
        rng.shuffle(pool)
        for i in itertools.count():
            yield pool[i % len(pool)]
    elif name == "pbt":
        syms = list(D.SYMBOLS)
        while True:
            on = [x for x in syms if rng.random() < 0.5] or [rng.choice(syms)]
            yield (), [rng.choice(on) for _ in range(rng.randint(1, 10))]
    elif name == "pac":
        while True:
            yield D.gen_churn(rng, PAC_CHURN)
    else:
        raise ValueError(name)


class Coverage:
    """Line-to-line edge coverage of code executed from exec'd harness source."""

    def __init__(self):
        self.edges = set()

    def run(self, D, cls, s):
        new, last = set(), {}

        def tracer(frame, event, arg):
            if frame.f_code.co_filename != "<string>":
                return None
            if event == "line":
                k = id(frame)
                e = (frame.f_code.co_name, last.get(k), frame.f_lineno)
                last[k] = frame.f_lineno
                if e not in self.edges:
                    new.add(e)
            return tracer

        sys.settrace(tracer)
        try:
            svc = D.run_sequence(cls, s)
        finally:
            sys.settrace(None)
        self.edges |= new
        return svc, bool(new)


def fuzz_stream(D, cls, rng, maxlen=10):
    syms = list(D.SYMBOLS)
    cov, corpus = Coverage(), []
    seeds = [D.gen_normal(rng)[1] for _ in range(4)]
    while True:
        if seeds:
            s = seeds.pop(0)
        else:
            s = list(rng.choice(corpus)) if corpus else [rng.choice(syms)]
            for _ in range(rng.randint(1, 3)):
                op = rng.randrange(5)
                if op == 0 or not s:
                    s.insert(rng.randint(0, len(s)), rng.choice(syms))
                elif op == 1 and len(s) > 1:
                    del s[rng.randrange(len(s))]
                elif op == 2:
                    s[rng.randrange(len(s))] = rng.choice(syms)
                elif op == 3:
                    i = rng.randrange(len(s)); j = rng.randint(i, len(s))
                    s[j:j] = s[i:j]
                else:
                    o = rng.choice(corpus) if corpus else [rng.choice(syms)]
                    s = s[:rng.randint(0, len(s))] + list(o[rng.randint(0, len(o)):])
            s = s[:maxlen] or [rng.choice(syms)]
        svc, novel = cov.run(D, cls, s)
        if novel:
            corpus.append(list(s))
        yield (), s, svc


# ------------------------------------------------------------------ runner
def first_detection(name, D, cls, seed, cap=CAP, seed_cls=None):
    """Run one stream. Returns dict(actions=actions spent up to and including the first
    violating sequence, or None if none within the cap; length of the shrunk
    counterexample for pbt; episodes used for pac)."""
    rng = random.Random(seed)
    used, n = 0, 0
    gen = fuzz_stream(D, cls, rng) if name == "fuzz" else gen_stream(name, D, cls, rng)
    for item in gen:
        if name == "fuzz":
            pre, s, svc = item
        else:
            pre, s = item
            svc = D.run_sequence(cls, s, pre)
        cost = len(pre) + len(s)
        if used + cost > cap or (name == "pac" and n >= PAC_N):
            return dict(actions=None, used=used, episodes=n)
        used += cost
        n += 1
        if name == "differential":
            ref = list(effects(D, D.run_sequence(seed_cls, s, pre)))
            hit = False
            for e in effects(D, svc):
                if e in ref:
                    ref.remove(e)
                else:
                    hit = True
                    break
        else:
            hit = bool(D.violations(svc))
        if hit:
            out = dict(actions=used, used=used, episodes=n)
            if name == "pbt":
                out["shrunk"] = len(shrink(D, cls, s))
                out["raw"] = len(s)
            return out
    return None


# ------------------------------------------------------------------ static check
def _svc_call(node, names):
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in names):
        return False
    v = node.func.value
    return (isinstance(v, ast.Attribute) and v.attr == "svc") or (isinstance(v, ast.Name) and v.id == "svc")


def _self_call(node):
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "self"):
        return node.func.attr
    return None


def _targets(t):
    if isinstance(t, ast.Name):
        yield t.id
    elif isinstance(t, (ast.Tuple, ast.List)):
        for e in t.elts:
            yield from _targets(e)
    elif isinstance(t, ast.Starred):
        yield from _targets(t.value)


class _Method:
    def __init__(self, fn):
        self.fn, self.tainted = fn, set()


def class_methods(code, D):
    """Methods of the Candidate class, merged with any known parent class it extends
    (child methods override)."""
    tree = ast.parse(textwrap.dedent(code))
    classes = {c.name: c for c in tree.body if isinstance(c, ast.ClassDef)}
    cand = classes.get("Candidate") or list(classes.values())[-1]
    meths = {}

    def add(c):
        for b in c.bases:
            nm = b.id if isinstance(b, ast.Name) else None
            if nm in classes and nm != c.name:
                add(classes[nm])
            elif nm in D.mock_parents:
                src = textwrap.dedent(inspect.getsource(D.mock_parents[nm]))
                add(ast.parse(src).body[0])
        for f in c.body:
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                meths[f.name] = f
    add(cand)
    for f in [D.Harness]:                                   # base helpers such as _ok
        for g in ast.parse(textwrap.dedent(inspect.getsource(f))).body[0].body:
            if isinstance(g, ast.FunctionDef):
                meths.setdefault(g.name, g)
    return meths


def static_check(code, D):
    """Returns (flag, reasons)."""
    auth = AUTH[D.name]
    meths = class_methods(code, D)
    fresh_m = set()
    taint = {m: set() for m in meths}

    def fresh(expr, m):
        for n in ast.walk(expr):
            if _svc_call(n, auth):
                return True
            if isinstance(n, ast.Name) and n.id in taint[m]:
                return True
            if _self_call(n) in fresh_m:
                return True
        return False

    for _ in range(10):                                     # fixpoint: locals, then methods
        changed = False
        for m, fn in meths.items():
            for n in ast.walk(fn):
                pairs = []
                if isinstance(n, ast.Assign):
                    pairs = [(t, n.value) for t in n.targets]
                elif isinstance(n, (ast.AugAssign, ast.AnnAssign)) and n.value is not None:
                    pairs = [(n.target, n.value)]
                elif isinstance(n, (ast.For, ast.comprehension)):
                    pairs = [(n.target, n.iter)]
                elif isinstance(n, ast.NamedExpr):
                    pairs = [(n.target, n.value)]
                for t, v in pairs:
                    if fresh(v, m):
                        for nm in _targets(t):
                            if nm not in taint[m]:
                                taint[m].add(nm); changed = True
            rets = [n.value for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value is not None]
            if rets and all(fresh(r, m) for r in rets) and m not in fresh_m:
                fresh_m.add(m); changed = True
        if not changed:
            break

    def exits(body):
        return bool(body) and isinstance(body[-1], (ast.Return, ast.Continue, ast.Break, ast.Raise))

    def guarded(fn, m, target):
        """Is `target` (a node inside fn) dominated by a fresh guard?"""
        def walk(stmts, path_ok):
            for st in stmts:
                if path_ok:
                    return True
                # does this statement contain the target?
                if not any(x is target for x in ast.walk(st)):
                    if isinstance(st, ast.If) and fresh(st.test, m) and (exits(st.body) or exits(st.orelse)):
                        path_ok = True
                    if isinstance(st, ast.Assert) and fresh(st.test, m):
                        path_ok = True
                    continue
                return inner(st, path_ok)
            return path_ok

        def inner(node, ok):
            if ok:
                return True
            if node is target:
                return False
            if isinstance(node, (ast.If, ast.While)):
                if any(x is target for x in ast.walk(node.test)):
                    return inner_expr(node.test, False)
                g = fresh(node.test, m)
                for blk in (node.body, node.orelse):
                    if any(x is target for s in blk for x in ast.walk(s)):
                        return walk(blk, g)
            if isinstance(node, (ast.For, ast.With, ast.Try)):
                for blk in [getattr(node, k) for k in ("body", "orelse", "finalbody") if hasattr(node, k)] + \
                        [h.body for h in getattr(node, "handlers", [])]:
                    if any(x is target for s in blk for x in ast.walk(s)):
                        return walk(blk, False)
            if isinstance(node, (ast.FunctionDef, ast.Lambda)):
                return False
            for ch in ast.iter_child_nodes(node):
                if any(x is target for x in ast.walk(ch)):
                    if isinstance(ch, ast.expr):
                        return inner_expr(ch, False)
                    return inner(ch, False)
            return False

        def inner_expr(e, ok):
            if ok:
                return True
            if e is target:
                return False
            if isinstance(e, ast.BoolOp):
                seen = False
                for v in e.values:
                    if any(x is target for x in ast.walk(v)):
                        return inner_expr(v, seen)
                    seen = seen or fresh(v, m)
            if isinstance(e, ast.IfExp):
                if any(x is target for x in ast.walk(e.body)) or any(x is target for x in ast.walk(e.orelse)):
                    br = e.body if any(x is target for x in ast.walk(e.body)) else e.orelse
                    return inner_expr(br, fresh(e.test, m))
            if isinstance(e, ast.Lambda):
                return False
            for ch in ast.iter_child_nodes(e):
                if any(x is target for x in ast.walk(ch)):
                    return inner_expr(ch, False)
            return False

        return walk(fn.body, False)

    reasons = []

    def callers_ok(m, depth=0):
        if m in ("submit", "flush"):
            return False
        calls = [(c, fn, n) for c, fn in meths.items() for n in ast.walk(fn) if _self_call(n) == m]
        if not calls:
            return True                                       # dead helper
        if depth > 4:
            return False
        return all(guarded(fn, c, n) or callers_ok(c, depth + 1) for c, fn, n in calls)

    for m, fn in meths.items():
        for n in ast.walk(fn):
            if _svc_call(n, {EFFECT}):
                if guarded(fn, m, n):
                    continue
                if callers_ok(m):
                    continue
                reasons.append(f"{m}: effect not dominated by a fresh server check")
    return bool(reasons), reasons
