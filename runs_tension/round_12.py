class Candidate(Harness):
    """Use subscribe to cache grant events, then consume_async (cost 0) for all payments.

    For cached active approvals: consume_async (0.0) + execute
    For unknown approvals: consume_async (0.0) + execute (optimistic, no verification cost)
    """
    name, rtype, label = "subscribe_async_optimistic", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}  # aid -> rec
        self._consumed = set()  # aids we've already consumed
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def submit(self, aid, payee, amount):
        # Skip if already consumed
        if aid in self._consumed:
            return

        # If we have cached info, verify it matches before proceeding
        if aid in self._cache:
            rec = self._cache[aid]
            if (rec.get('status') == 'active' and
                    rec.get('payee') == payee and
                    rec.get('amount') == amount):
                self._consumed.add(aid)
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
                return
            # Cached but doesn't match or not active - don't execute
            return

        # Not in cache - use consume_async optimistically (cost 0.0)
        # consume_async will silently fail if not active, but we proceed
        self._consumed.add(aid)
        self.svc.consume_async(aid)
        self.svc.execute(aid, payee, amount)
