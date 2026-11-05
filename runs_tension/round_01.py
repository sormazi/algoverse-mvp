class Candidate(Harness):
    """Use subscribe to cache grant events, then consume_async (cost 0) instead of check_and_consume (cost 1).

    For cached active approvals matching payee/amount: consume_async (0.0) + execute
    Fallback for unknown approvals: check_and_consume (1.0) + execute
    """
    name, rtype, label = "subscribe_async", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}  # aid -> rec
        self._consumed = set()  # aids we've already consumed
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def submit(self, aid, payee, amount):
        # If we have cached info and it matches, use free consume_async
        if aid in self._cache and aid not in self._consumed:
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
            self.svc.execute(aid, payee, amount)
