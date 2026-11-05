class Candidate(Harness):
    """Use subscribe to cache grants/revokes. Use check_and_consume atomically for safety."""
    name, rtype, label = "subscribe_check_and_consume", "optimized", "safe"

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
        if cached is not None:
            if cached.get('payee') != payee or cached.get('amount') != amount:
                return  # mismatch, don't pay
        # Use atomic check_and_consume for correctness
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self._consumed.add(aid)
            self.svc.execute(aid, payee, amount)
