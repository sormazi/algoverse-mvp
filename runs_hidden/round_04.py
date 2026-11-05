class Candidate(Harness):
    """Use subscribe to cache grant events, consume_async (cost 0.0) for cached approvals.

    After consume_async, verify with version() (cost 0.1) that consumption happened.
    Fallback: check_and_consume (cost 1.0) if not in cache.
    """
    name, rtype, label = "candidate", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}  # aid -> rec
        self.svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec
        elif kind == 'revoke':
            self._cache.pop(aid, None)

    def submit(self, aid, payee, amount):
        rec = self._cache.pop(aid, None)
        if rec is not None:
            if rec.get('payee') == payee and rec.get('amount') == amount:
                ver_before = rec.get('ver')
                self.svc.consume_async(aid)
                ver_after = self.svc.version(aid)
                # If version changed, consume_async succeeded
                if ver_after != ver_before:
                    self.svc.execute(aid, payee, amount)
                    return
                # else fall through to check_and_consume
        # Fallback: atomic check-and-consume (cost 1.0)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
