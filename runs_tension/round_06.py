class Candidate(Harness):
    """Use subscribe to cache grant events, consume_async for cached fresh grants."""
    name, rtype, label = "subscribe_async_v2", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}   # aid -> rec
        self._submitted = set()  # aids we've submitted
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def submit(self, aid, payee, amount):
        # Prevent double-payment for same aid
        if aid in self._submitted:
            return
        self._submitted.add(aid)

        if aid in self._cache:
            rec = self._cache[aid]
            if (rec.get('status') == 'active' and
                    rec.get('payee') == payee and
                    rec.get('amount') == amount):
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
                return
        # Fallback: atomic check_and_consume (cost 1.0)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
