class Candidate(Harness):
    """Subscribe to cache approvals (cost 0), consume_async if cached (cost 0), queue uncached for flush."""
    name, rtype, label = "subscribe_consume_async_v2", "optimized", "safe"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}       # aid -> rec
        self._revoked = set()
        self._consumed = set()
        self._pending = []     # (aid, payee, amount) not yet cached
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
            self._consumed.add(aid)
            self.svc.consume_async(aid)  # cost 0.0
            self.svc.execute(aid, payee, amount)
        else:
            # Queue for flush - subscribe event may not have fired yet
            self._pending.append((aid, payee, amount))

    def flush(self):
        for aid, payee, amount in self._pending:
            if aid in self._revoked or aid in self._consumed:
                continue
            cached = self._cache.get(aid)
            if cached and cached.get('payee') == payee and cached.get('amount') == amount:
                self._consumed.add(aid)
                self.svc.consume_async(aid)  # cost 0.0
                self.svc.execute(aid, payee, amount)
            else:
                # Last resort: atomic check_and_consume
                if self.svc.check_and_consume(aid, payee=payee, amount=amount):  # cost 1.0
                    self._consumed.add(aid)
                    self.svc.execute(aid, payee, amount)
        self._pending.clear()
