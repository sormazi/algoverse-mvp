class Candidate(Harness):
    """Subscribe to cache approvals (cost 0), batch process in flush."""
    name, rtype, label = "subscribe_flush_zero", "optimized", "safe"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}   # aid -> rec
        self._revoked = set()
        self._consumed = set()
        self._pending = []  # (aid, payee, amount)
        self.svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec
            self._revoked.discard(aid)
        elif kind == 'revoke':
            self._revoked.add(aid)
            self._cache.pop(aid, None)

    def submit(self, aid, payee, amount):
        self._pending.append((aid, payee, amount))

    def flush(self):
        for aid, payee, amount in self._pending:
            if aid in self._revoked or aid in self._consumed:
                continue
            cached = self._cache.get(aid)
            if cached and cached.get('payee') == payee and cached.get('amount') == amount:
                if aid not in self._revoked and aid not in self._consumed:
                    self._consumed.add(aid)
                    self.svc.consume_async(aid)  # cost 0.0
                    self.svc.execute(aid, payee, amount)
            else:
                # Fallback: use atomic check_and_consume
                if self.svc.check_and_consume(aid, payee=payee, amount=amount):  # cost 1.0
                    self._consumed.add(aid)
                    self.svc.execute(aid, payee, amount)
        self._pending.clear()
