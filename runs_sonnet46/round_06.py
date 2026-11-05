class Candidate(Harness):
    """Subscribe to cache approvals; use check_and_consume atomically for safety."""
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
        # Never pay revoked or already consumed
        if aid in self._revoked or aid in self._consumed:
            return

        # Use atomic check_and_consume to safely mark approval used
        # This costs 1.0 but is always safe (atomic, handles races)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):  # cost 1.0
            self._consumed.add(aid)
            self.svc.execute(aid, payee, amount)
        # If check_and_consume returns False, approval invalid/mismatched/revoked - skip

    def flush(self):
        pass
