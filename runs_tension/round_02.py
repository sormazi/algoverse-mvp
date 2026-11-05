class Candidate(Harness):
    """Queue all submissions, process in flush() after subscribe cache is populated.

    By deferring to flush(), all grant events should be cached via subscribe,
    allowing consume_async (0.0) for all known approvals.
    For any remaining unknowns, use check_batch (1.0 per call for many) then consume_async.
    """
    name, rtype, label = "subscribe_async_batched", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}   # aid -> rec
        self._consumed = set()
        self._queue = []   # (aid, payee, amount)
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def submit(self, aid, payee, amount):
        self._queue.append((aid, payee, amount))

    def flush(self):
        # First pass: handle all cached approvals with consume_async (cost 0)
        unknown = []
        for aid, payee, amount in self._queue:
            if aid in self._consumed:
                continue
            if aid in self._cache:
                rec = self._cache[aid]
                if (rec.get('status') == 'active' and
                        rec.get('payee') == payee and
                        rec.get('amount') == amount):
                    self._consumed.add(aid)
                    self.svc.consume_async(aid)
                    self.svc.execute(aid, payee, amount)
                else:
                    # Cached but doesn't match or not active - skip (invalid payment)
                    pass
            else:
                unknown.append((aid, payee, amount))

        # Second pass: batch check unknowns (1 call covers all unknown aids)
        if unknown:
            aids = [aid for aid, _, _ in unknown]
            batch = self.svc.check_batch(aids)  # cost 1.0 total for this call
            # Update cache with batch results
            for aid, rec in batch.items():
                self._cache[aid] = rec
            # Now process unknowns using consume_async for active matches
            for aid, payee, amount in unknown:
                if aid in self._consumed:
                    continue
                rec = batch.get(aid, {})
                if (rec.get('status') == 'active' and
                        rec.get('payee') == payee and
                        rec.get('amount') == amount):
                    self._consumed.add(aid)
                    self.svc.consume_async(aid)
                    self.svc.execute(aid, payee, amount)

        self._queue.clear()
