class Candidate(Harness):
    """Use subscribe to cache grant events; consume_async for cached active approvals.
    Only execute after confirmed consumption.
    For cached approvals: consume_async is safe because grant events are authoritative
    and we track consumed aids to prevent double-spend.
    For unknown approvals: check_and_consume atomic fallback.
    """
    name, rtype, label = "subscribe_async_v2", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}   # aid -> rec
        self._consumed = set()
        self._pending = []  # (aid, payee, amount) to handle in flush
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def submit(self, aid, payee, amount):
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
