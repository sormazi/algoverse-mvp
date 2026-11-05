class Candidate(Harness):
    """Use subscribe to cache grant events, then verify with version + consume_async.

    Cost: 0.1 per payment (version check) when approval is pre-cached via subscribe.
    Fallback: check_and_consume (1.0) if not in cache.
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
        rec = self._cache.get(aid)
        if rec and rec.get('payee') == payee and rec.get('amount') == amount:
            # Verify version hasn't changed (cost 0.1), then consume_async (cost 0.0)
            current_ver = self.svc.version(aid)
            if current_ver == rec.get('ver'):
                self._cache.pop(aid, None)
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
                return
        # Fallback
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
