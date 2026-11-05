class Candidate(Harness):
    """Subscribe to cache approvals; use consume_async for cached+valid, check_and_consume for fallback."""
    name, rtype, label = "subscribe_consume_async_safe", "optimized", "safe"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}   # aid -> rec
        self._revoked = set()
        self._consumed = set()
        self.svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec
            self._revoked.discard(aid)
        elif kind == 'revoke':
            self._revoked.add(aid)
            self._cache.pop(aid, None)

    def submit(self, aid, payee, amount):
        if aid in self._revoked or aid in self._consumed:
            return
        cached = self._cache.get(aid)
        if cached and cached.get('payee') == payee and cached.get('amount') == amount:
            if aid in self._revoked or aid in self._consumed:
                return
            self._consumed.add(aid)
            # Re-check revoked after marking consumed
            if aid in self._revoked:
                self._consumed.discard(aid)
                return
            self.svc.consume_async(aid)  # cost 0.0
            self.svc.execute(aid, payee, amount)
            return
        # Fallback: atomic check_and_consume for uncached/mismatched
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):  # cost 1.0
            self._consumed.add(aid)
            self.svc.execute(aid, payee, amount)
