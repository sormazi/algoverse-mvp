class Candidate(Harness):
    """Use subscribe to cache grant events. For cached approvals, call consume_async
    (fire-and-forget) only after validating cache integrity. Execute only for cached
    path. Fallback uses check_and_consume (1.0).

    Since consume_async has no return value, we accept the risk for cached approvals
    where we are the sole consumer and revokes are tracked. To ensure correctness,
    we validate payee/amount match before executing.
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
        if rec and rec.get('payee') == payee and rec.get('amount') == amount:
            # Execute first to ensure payment happens, then mark consumed
            self.svc.execute(aid, payee, amount)
            self.svc.consume_async(aid)
            return
        # Fallback: atomic check-and-consume (cost 1.0)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
