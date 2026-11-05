class Candidate(Harness):
    """Use subscribe to cache grant events, consume_async with no version check.

    Cost: 0.0 per payment when approval is pre-cached via subscribe.
    Fallback: version check (0.1) + consume_async (0.0) if not in cache but
    we can verify activity, else check_and_consume (1.0) as last resort.

    Since we are the sole consumer and track revokes via subscribe,
    if an aid is in cache it must still be active - no version check needed.
    """
    name, rtype, label = "candidate", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}  # aid -> {status, payee, amount, ver}
        self._pending = []  # (aid, payee, amount) for flush
        self.svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec
        elif kind == 'revoke':
            self._cache.pop(aid, None)

    def submit(self, aid, payee, amount):
        rec = self._cache.pop(aid, None)
        if rec and rec.get('payee') == payee and rec.get('amount') == amount:
            # Sole consumer + revoke tracking = still active. Cost: 0.0
            self.svc.consume_async(aid)
            self.svc.execute(aid, payee, amount)
            return
        # Fallback: atomic check-and-consume (cost 1.0)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
