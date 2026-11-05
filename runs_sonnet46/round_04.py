class Candidate(Harness):
    """Use subscribe to cache approvals, verify payee/amount from cache, then consume (returns bool) for safety."""
    name, rtype, label = "subscribe_consume_safe", "optimized", "safe"

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
            # We know payee/amount match from cache; use check_and_consume atomically
            # to handle any race with revoke between cache read and consume
            if aid not in self._revoked and aid not in self._consumed:
                if self.svc.check_and_consume(aid, payee=payee, amount=amount):  # cost 1.0, atomic
                    self._consumed.add(aid)
                    self.svc.execute(aid, payee, amount)
                return
        # Fallback: no cache hit, use check_and_consume
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):  # cost 1.0
            self._consumed.add(aid)
            self.svc.execute(aid, payee, amount)
