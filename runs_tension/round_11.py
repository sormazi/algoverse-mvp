class Candidate(Harness):
    """Use subscribe to cache grant events, consume (cost 1.0) for verification before execute.
    But for cached fresh grants use consume_async (0.0) only if very recently granted."""
    name, rtype, label = "subscribe_consume", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}  # aid -> rec
        self._consumed = set()
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
                # consume_async is free but fire-and-forget; use consume for safety
                if self.svc.consume(aid):
                    self.svc.execute(aid, payee, amount)
                return
        # Fallback: atomic check_and_consume (cost 1.0)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
