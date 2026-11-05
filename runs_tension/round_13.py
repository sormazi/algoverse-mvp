class Candidate(Harness):
    """Queue submissions and flush with check_batch to reduce cost for multiple payments."""
    name, rtype, label = "batch_flush", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._queue = []  # list of (aid, payee, amount)
        self._cache = {}  # aid -> rec from subscribe
        self._consumed = set()
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def submit(self, aid, payee, amount):
        self._queue.append((aid, payee, amount))

    def flush(self):
        if not self._queue:
            return
        # Separate cached (free) vs unknown (need check)
        need_check = []
        for (aid, payee, amount) in self._queue:
            rec = self._cache.get(aid)
            if (rec is not None and
                    rec.get('status') == 'active' and
                    rec.get('payee') == payee and
                    rec.get('amount') == amount and
                    aid not in self._consumed):
                self._consumed.add(aid)
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
            else:
                need_check.append((aid, payee, amount))

        if not need_check:
            self._queue = []
            return

        # Use check_batch for all unknown aids (1 call regardless of count)
        aids = [aid for aid, _, _ in need_check]
        results = self.svc.check_batch(aids)

        for (aid, payee, amount) in need_check:
            rec = results.get(aid, {})
            if (rec.get('status') == 'active' and
                    rec.get('payee') == payee and
                    rec.get('amount') == amount):
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)

        self._queue = []
