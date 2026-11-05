class Candidate(Harness):
    """Use atomic check_and_consume to replace separate check+consume calls.

    Original: check (1.0) + consume (1.0) = 2.0 per payment
    New:      check_and_consume (1.0) = 1.0 per payment

    check_and_consume atomically verifies status==active, matches payee and amount,
    then marks it used — returning True only if all conditions are met.
    """
    name, rtype, label = "candidate", "optimized", "safe"

    def submit(self, aid, payee, amount):
        if self.svc.check_and_consume(aid, payee=payee, amount=amount):
            self.svc.execute(aid, payee, amount)
