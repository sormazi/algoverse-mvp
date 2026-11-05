class Candidate(Harness):
    """Use subscribe to cache grant events. For cached active approvals, use
    check_and_consume (atomic, safe). This maintains correctness while the
    subscribe cache helps us avoid extra check calls.

    Cost: 1.0 per payment (check_and_consume), but subscribe is free.
    """
    name, rtype, label = "subscribe_safe", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}  # aid -> rec
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def submit(self, aid, payee, amount):
        # Use atomic check_and_consume - safe against races and stale state
        # check_and_consume validates payee/amount atomically
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)

    def flush(self):
        pass
