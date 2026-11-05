"""
Domain registry. A domain bundles the world, the contract oracle, the evaluators
and the prompt text, so llm_edits.py and self_agent.py can run on any of them.

  payments  (default) testbed.py + run.py, the original MVP world
  sessions  sessions.py, login tokens with logout / password change / expiry / scope

Every domain object exposes:
  Harness, Seed, SYMBOLS, run_sequence, violations, valid_requests_unpaid,
  exhaustive, gen_normal, gen_random, SINGLE_PROBES, TRANSITION, fill_budget,
  flags, presence_audit, efficiency, MAXLEN, SEEDS,
  api_doc(tension) -> str, UNIT, JOB, TOOL, CALL_EXAMPLE, CALL_KEY,
  describe_queue(seq), run_episode(cls, seq, calls), oracle_calls(seq),
  is_request(sym), MOCK_POOL, mock_parents (names exec'd alongside mock replies)
"""
import itertools
from types import SimpleNamespace

NAMES = ["payments", "sessions"]


def get(name="payments"):
    if name == "payments":
        import testbed, run, llm_edits, self_agent
        return SimpleNamespace(
            name="payments", module=testbed,
            Harness=testbed.Harness, Seed=testbed.Seed, SYMBOLS=testbed.SYMBOLS,
            run_sequence=testbed.run_sequence, violations=testbed.violations,
            valid_requests_unpaid=testbed.valid_requests_unpaid,
            exhaustive=run.exhaustive, gen_normal=run.gen_normal, gen_random=run.gen_random,
            SINGLE_PROBES=run.SINGLE_PROBES, TRANSITION=run.TRANSITION,
            fill_budget=run.fill_budget, flags=run.flags,
            presence_audit=run.presence_audit, efficiency=run.efficiency,
            MAXLEN=run.MAXLEN, SEEDS=run.SEEDS,
            api_doc=lambda tension, cost_gap=1.0: llm_edits.make_api_doc(tension, cost_gap),
            UNIT="payment", JOB="an autonomous payment-processing agent",
            TOOL="pay(aid, payee, amount)",
            CALL_EXAMPLE='[{"aid": 1, "payee": "X", "amount": 50}]', CALL_KEY="aid",
            describe_queue=self_agent.describe_queue, run_episode=self_agent.run_episode,
            oracle_calls=self_agent.oracle_calls,
            is_request=lambda sym: testbed.SYMBOLS[sym][0] == "pay",
            MOCK_POOL=llm_edits.MOCK_POOL,
            mock_parents={n: getattr(testbed, n) for n in ("CacheSafe", "MoveSafe", "BatchSafe")},
            supports_tension=True)
    if name == "sessions":
        import sessions as S
        return SimpleNamespace(
            name="sessions", module=S,
            Harness=S.Harness, Seed=S.Seed, SYMBOLS=S.SYMBOLS,
            run_sequence=S.run_sequence, violations=S.violations,
            valid_requests_unpaid=S.valid_requests_unpaid,
            exhaustive=S.exhaustive, gen_normal=S.gen_normal, gen_random=S.gen_random,
            SINGLE_PROBES=S.SINGLE_PROBES, TRANSITION=S.TRANSITION,
            fill_budget=S.fill_budget, flags=S.flags,
            presence_audit=S.presence_audit, efficiency=S.efficiency,
            MAXLEN=S.MAXLEN, SEEDS=S.SEEDS,
            api_doc=lambda tension, cost_gap=1.0: S.API_DOC,
            UNIT=S.UNIT, JOB=S.JOB, TOOL=S.TOOL, CALL_EXAMPLE=S.CALL_EXAMPLE, CALL_KEY=S.CALL_KEY,
            describe_queue=S.describe_queue, run_episode=S.run_episode,
            oracle_calls=S.oracle_calls,
            is_request=lambda sym: S.SYMBOLS[sym][0] == "act",
            MOCK_POOL=S.MOCK_POOL,
            mock_parents={n: getattr(S, n) for n in ("BatchSafe",)},
            supports_tension=False)
    raise ValueError(f"unknown domain {name!r}; choose from {NAMES}")


def subtlety(D, cls):
    """How hidden is a bug? Over every sequence up to MAXLEN: the length of the
    shortest violating sequence and the fraction of sequences that violate."""
    syms, bad, total, shortest = list(D.SYMBOLS), 0, 0, None
    for L in range(1, D.MAXLEN + 1):
        for seq in itertools.product(syms, repeat=L):
            total += 1
            if D.violations(D.run_sequence(cls, seq)):
                bad += 1
                if shortest is None:
                    shortest = L
    return dict(shortest_len=shortest, violation_density=round(bad / total, 5))
