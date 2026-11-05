class Candidate(Harness):
    """Use subscribe to cache grant events, then consume_async (cost 0) for cached approvals.

    Fixes: track consumed set properly, handle duplicate submits, don't execute on failed consume.
    """
    name, rtype, label = "subscribe_async_v2", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}   # aid -> rec at grant time
        self._consumed = set()
        self._pending = []  # (aid, payee, amount) not yet resolved
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def submit(self, aid, payee, amount):
        if aid in self._consumed:
            # Already consumed, don't re-execute
            return
        if aid in self._cache:
            rec = self._cache[aid]
            if (rec.get('status') == 'active' and
                    rec.get('payee') == payee and
                    rec.get('amount') == amount):
                self._consumed.add(aid)
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
                return
        # Fallback: atomic check_and_consume (cost 1.0)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self._consumed.add(aid)
            self.svc.execute(aid, payee, amount)
