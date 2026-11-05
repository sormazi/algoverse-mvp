class Candidate(Harness):
    """Subscribe to cache approvals (cost 0), consume_async for cached, queue uncached for flush."""
    name, rtype, label = "subscribe_consume_async_queued", "optimized", "safe"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}      # aid -> rec
        self._revoked = set()
        self._consumed = set()
        self._pending = []    # list of (aid, payee, amount) not yet resolved
        self.svc.subscribe(self._on_event)

    def _on_event(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec
            self._revoked.discard(aid)
        elif kind == 'revoke':
            self._revoked.add(aid)
            self._cache.pop(aid, None)

    def _try_execute(self, aid, payee, amount):
        """Try to execute using cache only. Returns True if handled, False if should retry."""
        if aid in self._revoked or aid in self._consumed:
            return True  # terminal state, don't retry
        cached = self._cache.get(aid)
        if cached is not None:
            if cached.get('payee') == payee and cached.get('amount') == amount:
                self._consumed.add(aid)
                self.svc.consume_async(aid)  # cost 0.0
                self.svc.execute(aid, payee, amount)
            # else: cached but mismatched - don't pay
            return True
        return False  # not yet cached

    def submit(self, aid, payee, amount):
        if not self._try_execute(aid, payee, amount):
            # Not in cache yet, queue for flush
            self._pending.append((aid, payee, amount))

    def flush(self):
        # Process pending items; by now all grant events should have fired
        # Multiple passes in case of ordering issues
        max_passes = 3
        for _ in range(max_passes):
            if not self._pending:
                break
            still_pending = []
            for aid, payee, amount in self._pending:
                if not self._try_execute(aid, payee, amount):
                    still_pending.append((aid, payee, amount))
            self._pending = still_pending

        # Any remaining truly uncached items - use check_and_consume as last resort
        for aid, payee, amount in self._pending:
            if aid not in self._revoked and aid not in self._consumed:
                if self.svc.check_and_consume(aid, payee=payee, amount=amount):  # cost 1.0
                    self._consumed.add(aid)
                    self.svc.execute(aid, payee, amount)
        self._pending = []
