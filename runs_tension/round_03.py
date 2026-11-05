class Candidate(Harness):
    """Use subscribe to cache grant events; consume_async (cost 0) for known grants.
    Queue unknown aids and process in flush() hoping they arrive via subscribe by then.
    """
    name, rtype, label = "subscribe_async_v2", "optimized", "safe"

    def __init__(self, svc):
        super().__init__(svc)
        self._cache = {}   # aid -> rec
        self._consumed = set()
        self._pending = []  # (aid, payee, amount) not yet resolved
        self.svc.subscribe(self._on_grant)

    def _on_grant(self, kind, aid, rec):
        if kind == 'grant':
            self._cache[aid] = rec

    def _try_process(self, aid, payee, amount):
        if aid in self._cache and aid not in self._consumed:
            rec = self._cache[aid]
            if (rec.get('status') == 'active' and
                    rec.get('payee') == payee and
                    rec.get('amount') == amount):
                self._consumed.add(aid)
                self.svc.consume_async(aid)
                self.svc.execute(aid, payee, amount)
                return True
        return False

    def submit(self, aid, payee, amount):
        if not self._try_process(aid, payee, amount):
            self._pending.append((aid, payee, amount))

    def flush(self):
        for aid, payee, amount in self._pending:
            if not self._try_process(aid, payee, amount):
                # Final fallback: atomic check_and_consume
                if self.svc.check_and_consume(aid, payee=payee, amount=amount):
                    self.svc.execute(aid, payee, amount)
        self._pending.clear()
