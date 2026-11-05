class Candidate(Harness):
    """Use subscribe to cache grant events; batch check_batch for unknowns to amortize costs."""
    name, rtype, label = "subscribe_async_batch", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}       # aid -> rec
        self._consumed = set() # aids we've already consumed
        self._pending = []     # (aid, payee, amount) not yet resolved
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def submit(self, aid, payee, amount):
        if aid in self._cache and aid not in self._consumed:
            rec = self._cache[aid]
            if (rec.get('status') == 'active' and
                    rec.get('payee') == payee and
                    rec.get('amount') == amount):
                self._consumed.add(aid)
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
                return
        # Queue unknown/mismatched approvals for batch processing
        self._pending.append((aid, payee, amount))

    def flush(self):
        if not self._pending:
            return
        # Batch check all pending aids in one call (cost 1.0 total, not per item)
        aids = [aid for aid, _, _ in self._pending]
        results = self.svc.check_batch(aids)  # cost 1.0 for the whole batch
        for aid, payee, amount in self._pending:
            rec = results.get(aid, {})
            if (rec.get('status') == 'active' and
                    rec.get('payee') == payee and
                    rec.get('amount') == amount):
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
        self._pending.clear()
