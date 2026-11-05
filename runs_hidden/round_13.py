class Candidate(Harness):
    """Use subscribe to cache grant events, consume_async with no version check.

    Cost: 0.0 per payment when approval is pre-cached via subscribe.
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
        rec = self._cache.pop(aid, None)
        if (rec is not None
                and rec.get('status') == 'active'
                and rec.get('payee') == payee
                and rec.get('amount') == amount):
            # Sole consumer + revoke tracking => still active. Cost: 0.0
            self.svc.consume_async(aid)
            self.svc.execute(aid, payee, amount)
            return
        # Fallback: atomic check-and-consume (cost 1.0)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
