class Candidate(Harness):
    """Use atomic check_and_consume to replace separate check + consume calls.

    Original: check (1.0) + consume (1.0) = 2.0 per payment
    New:      check_and_consume (1.0) = 1.0 per payment
    """
    name, rtype, label = "check_and_consume", "optimized", "safe"

    def submit(self, aid, payee, amount):
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
