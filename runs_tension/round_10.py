class Candidate(Harness):
    """Queue submissions, batch-check unknowns, consume_async confirmed actives."""
    name, rtype, label = "subscribe_batch_async", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}
        self._queue = []  # (aid, payee, amount)
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def submit(self, aid, payee, amount):
        self._queue.append((aid, payee, amount))

    def flush(self):
        if not self._queue:
            return
        # Find aids not in cache
        unknown = [aid for aid, _, _ in self._queue if aid not in self._cache]
        if unknown:
            # One call for all unknowns: cost 1.0 total (not per aid)
            results = self.svc.check_batch(unknown)
            self._cache.update(results)
        # Now process all
        for aid, payee, amount in self._queue:
            rec = self._cache.get(aid, {})
            if (rec.get('status') == 'active' and
                    rec.get('payee') == payee and
                    rec.get('amount') == amount):
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
            else:
                if self.svc.check_and_consume(aid, payee=payee, amount=amount):
                    self.svc.execute(aid, payee, amount)
        self._queue.clear()
