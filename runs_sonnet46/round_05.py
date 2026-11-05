class Candidate(Harness):
    """Queue uncached submissions; process on grant event (cost 0). Fallback in flush."""
    name, rtype, label = "subscribe_queue_zero", "optimized", "safe"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}       # aid -> rec
        self._revoked = set()
        self._consumed = set()
        self._pending = {}     # aid -> (payee, amount) for uncached submissions
        self.svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec
            self._revoked.discard(aid)
            # Process any pending submission for this aid
            if aid in self._pending:
                payee, amount = self._pending.pop(aid)
                if (rec.get('payee') == payee and rec.get('amount') == amount
                        and aid not in self._consumed):
                    self._consumed.add(aid)
                    self.svc.consume_async(aid)
                    self.svc.execute(aid, payee, amount)
        elif kind == 'revoke':
            self._revoked.add(aid)
            self._cache.pop(aid, None)
            self._pending.pop(aid, None)

    def submit(self, aid, payee, amount):
        if aid in self._revoked or aid in self._consumed:
            return
        cached = self._cache.get(aid)
        if cached and cached.get('payee') == payee and cached.get('amount') == amount:
            self._consumed.add(aid)
            self.svc.consume_async(aid)
            self.svc.execute(aid, payee, amount)
            return
        # Queue for when grant event arrives
        self._pending[aid] = (payee, amount)

    def flush(self):
        # Handle any still-pending (no grant event received)
        for aid, (payee, amount) in list(self._pending.items()):
            if aid not in self._revoked and aid not in self._consumed:
                if self.svc.check_and_consume(aid, payee=payee, amount=amount):
                    self._consumed.add(aid)
                    self.svc.execute(aid, payee, amount)
        self._pending.clear()
