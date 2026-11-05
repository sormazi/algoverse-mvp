class Candidate(Harness):
    """Use subscribe to cache grant events. Verify with version() before consume_async.

    Cost: 0.1 per payment for cached approvals (version check).
    Fallback: check_and_consume (1.0) if not in cache or version mismatch.
    """
    name, rtype, label = "candidate", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}  # aid -> {status, payee, amount, ver}
        self.svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec
        elif kind == 'revoke':
            self._cache.pop(aid, None)

    def submit(self, aid, payee, amount):
        rec = self._cache.pop(aid, None)
        if rec and rec.get('payee') == payee and rec.get('amount') == amount:
            cached_ver = rec.get('ver')
            current_ver = self.svc.version(aid)  # cost 0.1
            if current_ver == cached_ver:
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
                return
        # Fallback: atomic check-and-consume (cost 1.0)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
