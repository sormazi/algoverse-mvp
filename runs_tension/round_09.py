class Candidate(Harness):
    """Use subscribe to cache grant events, then consume_async (cost 0) instead of check_and_consume (cost 1).
    Queue unknown approvals and retry in flush() after giving subscribe time to populate cache.
    """
    name, rtype, label = "subscribe_async_v2", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}   # aid -> rec
        self._consumed = set()
        self._pending = []  # (aid, payee, amount) not yet in cache
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def _try_submit(self, aid, payee, amount):
        if aid in self._cache and aid not in self._consumed:
            rec = self._cache[aid]
            if (rec.get('status') == 'active' and
                    rec.get('payee') == payee and
                    rec.get('amount') == amount):
                self._consumed.add(aid)
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
                return True
        return False

    def submit(self, aid, payee, amount):
        if not self._try_submit(aid, payee, amount):
            self._pending.append((aid, payee, amount))

    def flush(self):
        # Retry pending items now that more grant events may have arrived
        still_pending = []
        for aid, payee, amount in self._pending:
            if not self._try_submit(aid, payee, amount):
                still_pending.append((aid, payee, amount))
        # For truly unknown approvals, use check_and_consume as last resort
        for aid, payee, amount in still_pending:
            if aid not in self._consumed:
                if self.svc.check_and_consume(aid, payee=payee, amount=amount):
                    self._consumed.add(aid)
                    self.svc.execute(aid, payee, amount)
