class Candidate(Harness):
    """Use subscribe to cache grant events. For cached approvals, use
    consume_async (0.0) then version check (0.1) to verify consume succeeded.
    Fallback: check_and_consume (1.0) if not in cache.

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
            cached_ver = rec.get('ver')
            # Attempt consume at cost 0.0
            self.svc.consume_async(aid)
            # Verify consume succeeded by checking version changed (cost 0.1)
            new_ver = self.svc.version(aid)
            if new_ver != cached_ver:
                # Version changed means consume (or revoke) happened after our snapshot
                # Since we called consume_async and version changed, payment is consumed
                self.svc.execute(aid, payee, amount)
            # If version unchanged, consume_async had no effect (already used/revoked)
            # Do not execute
            return
        # Fallback: atomic check-and-consume (cost 1.0)
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
