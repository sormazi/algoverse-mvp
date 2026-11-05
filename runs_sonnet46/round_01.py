class Candidate(Harness):
    """Subscribe to cache approvals (cost 0), use version to verify (cost 0.1), consume_async (cost 0)."""
    name, rtype, label = "subscribe_version_consume_async", "optimized", "safe"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}  # aid -> {payee, amount, ver}
        self._revoked = set()
        self.svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec
        elif kind == 'revoke':
            self._revoked.add(aid)
            self._cache.pop(aid, None)

    def submit(self, aid, payee, amount):
        if aid in self._revoked:
            return
        cached = self._cache.get(aid)
        if cached and cached.get('payee') == payee and cached.get('amount') == amount:
            current_ver = self.svc.version(aid)  # cost 0.1
            if cached.get('ver') == current_ver and aid not in self._revoked:
                self.svc.consume_async(aid)  # cost 0.0
                self.svc.execute(aid, payee, amount)
                return
        # Fallback to atomic check_and_consume
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):  # cost 1.0
            self.svc.execute(aid, payee, amount)
