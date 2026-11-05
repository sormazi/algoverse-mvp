class Candidate(Harness):
    """Subscribe to cache approvals; queue uncached submissions; process all in flush."""
    name, rtype, label = "subscribe_queue_flush_zero", "optimized", "safe"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}   # aid -> rec
        self._revoked = set()
        self._consumed = set()
        self._pending = []  # (aid, payee, amount) for uncached at submit time
        self.svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec
            self._revoked.discard(aid)
        elif kind == 'revoke':
            self._revoked.add(aid)
            self._cache.pop(aid, None)

    def _try_pay(self, aid, payee, amount):
        if aid in self._revoked or aid in self._consumed:
            return False
        cached = self._cache.get(aid)
        if cached and cached.get('payee') == payee and cached.get('amount') == amount:
            self._consumed.add(aid)
            self.svc.consume_async(aid)  # cost 0.0
            self.svc.execute(aid, payee, amount)
            return True
        return False

    def submit(self, aid, payee, amount):
        if not self._try_pay(aid, payee, amount):
            # Not yet cached - queue for flush
            self._pending.append((aid, payee, amount))

    def flush(self):
        for aid, payee, amount in self._pending:
            if aid in self._consumed or aid in self._revoked:
                continue
            if not self._try_pay(aid, payee, amount):
                # Still not cached - must use check_and_consume as last resort
                if self.svc.check_and_consume(aid, payee=payee, amount=amount):
                    self._consumed.add(aid)
                    self.svc.execute(aid, payee, amount)
        self._pending.clear()
