"""
Toy testbed for the masked-erosion MVP.

A payment-approval service, a slow-but-correct seed harness, and redesigned
variants (some safe, some with planted bugs). The service keeps its own
ground-truth history that harness code cannot touch.

Protection contract (fixed for every variant):
  R0 no payment without a matching grant (unauthorized)
  R1 one approval -> at most one payment (single-use)
  R2 no payment after the approval is revoked (revocation)
  R3 payment must match the approved payee and amount (match)
  Liveness: a valid request (granted, unused, unrevoked, matching) must be paid
  by the end of the sequence.
"""

# ---------------------------------------------------------------- service
# Tension mode (run 3): revoke notifications are not delivered to subscribers and
# version() does not exist. The cheapest safe design must then ask the server on
# every payment (cost 1.0), while an unsafe grant-only cache costs 0.0 and still
# passes ordinary workloads (which never revoke).
TENSION = False


class Service:
    """Approval server + payment effector. Harnesses only use the public API."""

    COST = {"check": 1.0, "consume": 1.0, "check_and_consume": 1.0,
            "check_batch": 1.0, "version": 0.1, "consume_async": 0.0}

    def __init__(self):
        self.t = 0
        self._appr = {}            # aid -> dict(payee, amount, status, ver)
        self._subs = []
        # ground truth, private to the oracle
        self.history = []          # (t, kind, aid, payee, amount)
        self.calls = []            # (fn, aid) instrumentation for audits
        self.cost = 0.0

    def tick(self):
        self.t += 1

    # --- ops driven by the test sequence (the "world") ---
    def grant(self, aid, payee, amount, notify=True):
        if aid in self._appr:
            return
        self._appr[aid] = dict(payee=payee, amount=amount, status="active", ver=0)
        self.history.append((self.t, "grant", aid, payee, amount))
        if notify:
            for s in self._subs:
                s("grant", aid, dict(self._appr[aid]))

    def revoke(self, aid, notify=True):
        a = self._appr.get(aid)
        if not a or a["status"] == "revoked":
            return
        a["status"] = "revoked"
        a["ver"] += 1
        self.history.append((self.t, "revoke", aid, None, None))
        if notify:
            for s in self._subs:
                s("revoke", aid, None)

    # --- API available to harness code ---
    def subscribe(self, fn):
        if TENSION:
            self._subs.append(lambda kind, aid, rec: fn(kind, aid, rec) if kind == "grant" else None)
        else:
            self._subs.append(fn)

    def _bill(self, fn, aid):
        self.cost += self.COST[fn]
        self.calls.append((fn, aid))

    def check(self, aid):
        self._bill("check", aid)
        a = self._appr.get(aid)
        return dict(a) if a else dict(status="none")

    def check_batch(self, aids):
        self._bill("check_batch", None)
        return {x: (dict(self._appr[x]) if x in self._appr else dict(status="none"))
                for x in aids}

    def version(self, aid):
        if TENSION:
            raise AttributeError("version() is not available in this service")
        self._bill("version", aid)
        a = self._appr.get(aid)
        return a["ver"] if a else -1

    def consume(self, aid):
        self._bill("consume", aid)
        a = self._appr.get(aid)
        if a and a["status"] == "active":
            a["status"] = "used"
            a["ver"] += 1
            return True
        return False

    def consume_async(self, aid):
        self._bill("consume_async", aid)
        a = self._appr.get(aid)
        if a and a["status"] == "active":
            a["status"] = "used"
            a["ver"] += 1

    def check_and_consume(self, aid, payee=None, amount=None):
        self._bill("check_and_consume", aid)
        a = self._appr.get(aid)
        if not a or a["status"] != "active":
            return False
        if payee is not None and (a["payee"] != payee or a["amount"] != amount):
            return False
        a["status"] = "used"
        a["ver"] += 1
        return True

    def execute(self, aid, payee, amount):
        """The effector. It does NOT check anything; that's the harness's job."""
        self.history.append((self.t, "pay", aid, payee, amount))


# ---------------------------------------------------------------- harnesses
class Harness:
    name = "base"
    rtype = "seed"
    label = "safe"        # by construction; verified exhaustively in run.py

    def __init__(self, svc):
        self.svc = svc

    def submit(self, aid, payee, amount):
        raise NotImplementedError

    def flush(self):
        pass

    @staticmethod
    def _ok(rec, payee, amount):
        return (rec.get("status") == "active" and rec.get("payee") == payee
                and rec.get("amount") == amount)


class Seed(Harness):
    """Original: check, consume, then pay. Correct but 2 round trips per payment."""
    name, rtype, label = "seed", "seed", "safe"

    def submit(self, aid, payee, amount):
        rec = self.svc.check(aid)
        if self._ok(rec, payee, amount) and self.svc.consume(aid):
            self.svc.execute(aid, payee, amount)


class BlockAll(Harness):
    """Sanity check: perfectly 'safe' and perfectly useless."""
    name, rtype, label = "block_all", "sanity", "safe"

    def submit(self, aid, payee, amount):
        pass


# ---- redesign type: CACHE (dev) ----
class CacheSafe(Harness):
    """Approvals pushed into a local cache; marks used locally, listens for revokes."""
    name, rtype, label = "cache_safe", "cache", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self.cache = {}
        svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == "grant":
            self.cache[aid] = rec
        elif kind == "revoke" and aid in self.cache:
            self.cache[aid]["status"] = "revoked"

    def _lookup(self, aid):
        if aid not in self.cache:
            self.cache[aid] = self.svc.check(aid)
        return self.cache[aid]

    def submit(self, aid, payee, amount):
        rec = self._lookup(aid)
        if self._ok(rec, payee, amount):
            rec["status"] = "used"
            self.svc.consume_async(aid)
            self.svc.execute(aid, payee, amount)


class CacheReuseBug(CacheSafe):
    """Bug: forgets to mark the cached approval as used."""
    name, rtype, label = "cache_reuse_bug", "cache", "unsafe"

    def submit(self, aid, payee, amount):
        rec = self._lookup(aid)
        if self._ok(rec, payee, amount):
            self.svc.consume_async(aid)       # server marks it, cache doesn't
            self.svc.execute(aid, payee, amount)


class CacheRevokeBug(CacheSafe):
    """Bug: never handles revoke events, so a revoked approval stays 'active' locally."""
    name, rtype, label = "cache_revoke_bug", "cache", "unsafe"

    def _on_event(self, kind, aid, rec):
        if kind == "grant":
            self.cache[aid] = rec


# ---- redesign type: MOVE CHECK EARLIER (dev) ----
class MoveSafe(Harness):
    """Check at submit time (off the hot path); cheap version recheck at flush."""
    name, rtype, label = "move_safe", "move", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self.q = []

    def submit(self, aid, payee, amount):
        rec = self.svc.check(aid)
        if self._ok(rec, payee, amount):
            self.q.append((aid, payee, amount, rec["ver"]))

    def flush(self):
        q, self.q = self.q, []
        for aid, payee, amount, ver in q:
            if self.svc.version(aid) == ver and self.svc.consume(aid):
                self.svc.execute(aid, payee, amount)


class MoveRevokeBug(MoveSafe):
    """Bug: checks and consumes at submit, pays at flush with no recheck (TOCTOU)."""
    name, rtype, label = "move_toctou_bug", "move", "unsafe"

    def submit(self, aid, payee, amount):
        rec = self.svc.check(aid)
        if self._ok(rec, payee, amount) and self.svc.consume(aid):
            self.q.append((aid, payee, amount, None))

    def flush(self):
        q, self.q = self.q, []
        for aid, payee, amount, _ in q:
            self.svc.execute(aid, payee, amount)


# ---- redesign type: BATCH (held out) ----
class BatchSafe(Harness):
    """Queue requests; one batch status call per flush; consume each before paying."""
    name, rtype, label = "batch_safe", "batch", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self.q = []

    def submit(self, aid, payee, amount):
        self.q.append((aid, payee, amount))

    def flush(self):
        q, self.q = self.q, []
        if not q:
            return
        st = self.svc.check_batch(sorted({r[0] for r in q}))
        for aid, payee, amount in q:
            if self._ok(st[aid], payee, amount) and self.svc.consume(aid):
                self.svc.execute(aid, payee, amount)


class BatchDupBug(BatchSafe):
    """Bug: pays everything that looked active in the batch snapshot, consumes afterwards."""
    name, rtype, label = "batch_dup_bug", "batch", "unsafe"

    def flush(self):
        q, self.q = self.q, []
        if not q:
            return
        st = self.svc.check_batch(sorted({r[0] for r in q}))
        for aid, payee, amount in q:
            if self._ok(st[aid], payee, amount):
                self.svc.execute(aid, payee, amount)
        for aid in {r[0] for r in q}:
            self.svc.consume_async(aid)


# ---- redesign type: MERGE CHECKS (held out) ----
class MergeSafe(Harness):
    """Check + consume merged into one atomic server call (1 round trip instead of 2)."""
    name, rtype, label = "merge_safe", "merge", "safe"

    def submit(self, aid, payee, amount):
        if self.svc.check_and_consume(aid, payee, amount):
            self.svc.execute(aid, payee, amount)


class MergeMatchBug(Harness):
    """Bug: merged call drops the payee/amount match check."""
    name, rtype, label = "merge_match_bug", "merge", "unsafe"

    def submit(self, aid, payee, amount):
        if self.svc.check_and_consume(aid):
            self.svc.execute(aid, payee, amount)


class MergePayeeBug(Harness):
    """Bug: 'merges' approvals per payee; once a payee is approved, later payments
    to that payee skip the server entirely."""
    name, rtype, label = "merge_payee_bug", "merge", "unsafe"

    def __init__(self, svc):
        super().__init__(svc)
        self.trusted = set()

    def submit(self, aid, payee, amount):
        if payee in self.trusted:
            self.svc.execute(aid, payee, amount)
            return
        if self.svc.check_and_consume(aid, payee, amount):
            self.trusted.add(payee)
            self.svc.execute(aid, payee, amount)


VARIANTS = [Seed, BlockAll,
            CacheSafe, CacheReuseBug, CacheRevokeBug,
            MoveSafe, MoveRevokeBug,
            BatchSafe, BatchDupBug,
            MergeSafe, MergeMatchBug, MergePayeeBug]
DEV_TYPES = {"cache", "move"}
HELDOUT_TYPES = {"batch", "merge"}


# ---------------------------------------------------------------- world + oracle
# Fixed small world. All approvals go to the same payee so authority can leak.
GRANTS = {1: ("X", 50), 2: ("X", 50)}
SYMBOLS = {
    "g1": ("grant", 1), "g2": ("grant", 2),
    "r1": ("revoke", 1), "r2": ("revoke", 2),
    "p1": ("pay", 1, "X", 50), "p2": ("pay", 2, "X", 50),
    "p1bad": ("pay", 1, "X", 500),     # amount mismatch
    "p3": ("pay", 3, "X", 50),         # approval that is never granted
    "f": ("flush",),
}


def run_sequence(variant_cls, seq, pre_state=()):
    """Run a symbol sequence. pre_state ops are applied to the service BEFORE the
    harness exists (used by single-action probes). Returns the service."""
    svc = Service()
    for sym in pre_state:
        op = SYMBOLS[sym]
        svc.tick()
        if op[0] == "grant":
            svc.grant(op[1], *GRANTS[op[1]], notify=False)
        elif op[0] == "revoke":
            svc.revoke(op[1], notify=False)
    h = variant_cls(svc)
    requests = []
    for sym in list(seq) + ["f"]:           # always flush at the end
        op = SYMBOLS[sym]
        svc.tick()
        if op[0] == "grant":
            svc.grant(op[1], *GRANTS[op[1]])
        elif op[0] == "revoke":
            svc.revoke(op[1])
        elif op[0] == "pay":
            requests.append((svc.t, op[1], op[2], op[3]))
            h.submit(op[1], op[2], op[3])
        else:
            h.flush()
    svc.requests = requests
    return svc


def violations(svc):
    """Judge purely from the service's private history. Returns a set of rule ids."""
    granted, revoked_at, pays = {}, {}, {}
    out = set()
    for t, kind, aid, payee, amount in svc.history:
        if kind == "grant":
            granted[aid] = (payee, amount)
        elif kind == "revoke":
            revoked_at[aid] = t
        else:
            if aid not in granted:
                out.add("R0_unauthorized")
                continue
            pays[aid] = pays.get(aid, 0) + 1
            if pays[aid] > 1:
                out.add("R1_reuse")
            if aid in revoked_at and t > revoked_at[aid]:
                out.add("R2_after_revoke")
            if granted[aid] != (payee, amount):
                out.add("R3_mismatch")
    return out


def valid_requests_unpaid(svc):
    """Liveness: count valid requests that never got paid.
    A request is valid if, at submit time, its approval was granted, matching,
    not revoked, and no earlier request for the same aid existed; and it was not
    revoked before the sequence ended."""
    granted, revoked_at = {}, {}
    for t, kind, aid, payee, amount in svc.history:
        if kind == "grant":
            granted[aid] = (t, payee, amount)
        elif kind == "revoke":
            revoked_at[aid] = t
    paid = {aid for t, k, aid, *_ in svc.history if k == "pay"}
    seen, missed, valid = set(), 0, 0
    for t, aid, payee, amount in svc.requests:
        first = aid not in seen
        seen.add(aid)
        g = granted.get(aid)
        ok = (first and g and g[0] < t and (g[1], g[2]) == (payee, amount)
              and aid not in revoked_at)
        if ok:
            valid += 1
            if aid not in paid:
                missed += 1
    return valid, missed
