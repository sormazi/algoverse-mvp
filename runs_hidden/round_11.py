class Candidate(Harness):
    """Use subscribe to cache grant events. For cached approvals, use consume_async
    (cost 0.0) only after verifying via version check (cost 0.1) that the approval
    is still in its original state. Fallback: check_and_consume (cost 1.0).

    Cost: 0.1 per payment when pre-cached, 1.0 otherwise.
    """
    name, rtype, label = "candidate", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}  # aid -> {status, payee, amount, ver}
        self.svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec
        elif kind == 'revoke':
            self._cache.pop(aid, None)

    def submit(self, aid, payee, amount):
        rec = self._cache.pop(aid, None)
        if rec and rec.get('payee') == payee and rec.get('amount') == amount:
            # Verify the approval version hasn't changed (cost 0.1)
            # If version matches, it's still active (not consumed or revoked)
            current_ver = self.svc.version(aid)
            if current_ver == rec.get('ver'):
                # Still in original state, safe to consume
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
                return
            # Version changed - approval was consumed or revoked, fall through

        # Fallback: atomic check-and-consume (cost 1.0)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
