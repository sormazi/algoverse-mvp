class Candidate(Harness):
    """Use atomic check_and_consume to verify and mark used in one call (cost 1.0 vs 2.0)."""
    name, rtype, label = "check_and_consume", "optimized", "safe"

    def submit(self, aid, payee, amount):
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
