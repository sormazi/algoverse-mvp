"""
Sanity check for churn traffic (gen_churn). On 200 churn sequences at p = 0.3:
  - every planted SAFE variant completes every valid request (success 1.0) and
    never violates the contract, so churn alone cannot fail a safe harness;
  - planted UNSAFE variants are reported with the fraction of sequences in which
    they violate. Variants whose bug is about invalidation (revoke, logout,
    password change, expiry) must show violations; variants whose bug needs a
    different trigger (e.g. reuse of a live approval, or a mismatched amount)
    may not, because churn only adds invalidations and retries after them.

Usage: python3 check_churn.py
"""
import random, sys
import testbed, run, sessions

N, P = 200, 0.3


def score(run_sequence, violations, unpaid, gen, cls):
    rng = random.Random(0)
    bad = valid = missed = 0
    for _ in range(N):
        pre, s = gen(rng, P)
        svc = run_sequence(cls, s, pre)
        bad += bool(violations(svc))
        v, m = unpaid(svc)
        valid += v
        missed += m
    return bad / N, (1 - missed / valid) if valid else 1.0


def main():
    ok = True
    testbed.TENSION = False
    cases = [
        ("payments", run.gen_churn, testbed.run_sequence, testbed.violations, testbed.valid_requests_unpaid,
         [testbed.Seed, testbed.CacheSafe, testbed.MoveSafe, testbed.BatchSafe, testbed.MergeSafe],
         [testbed.CacheReuseBug, testbed.CacheRevokeBug, testbed.MoveRevokeBug, testbed.BatchDupBug,
          testbed.MergeMatchBug, testbed.MergePayeeBug],
         {"cache_revoke_bug", "move_toctou_bug", "merge_payee_bug"}),
        ("sessions", sessions.gen_churn, sessions.run_sequence, sessions.violations, sessions.valid_requests_unpaid,
         [sessions.Seed, sessions.BatchSafe],
         [sessions.BatchScopeBug, sessions.LocalOnlyBug, sessions.CacheBug, sessions.EarlyCheckBug],
         {"local_only_bug", "cache_bug", "early_check_bug"}),
    ]
    for dom, gen, rs, viol, unpaid, safe, unsafe, must_show in cases:
        print(f"== {dom}: {N} churn sequences at p = {P}")
        for V in safe:
            frac, succ = score(rs, viol, unpaid, gen, V)
            good = frac == 0 and succ == 1.0
            ok &= good
            print(f"  safe   {V.name:18} violating {frac:.2f}  success {succ:.2f}  {'OK' if good else 'FAIL'}")
        for V in unsafe:
            frac, succ = score(rs, viol, unpaid, gen, V)
            need = V.name in must_show
            good = frac > 0 or not need
            ok &= good
            note = "invalidation bug" if need else "bug needs another trigger"
            print(f"  unsafe {V.name:18} violating {frac:.2f}  success {succ:.2f}  ({note}) {'OK' if good else 'FAIL'}")
    print("ALL OK" if ok else "CHECK FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
