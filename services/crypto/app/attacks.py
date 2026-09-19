"""
Eve's attack toolkit. Kept server-side so a client can't just fabricate
a "correct" result — every attempt is verified here against the real n.
"""

from sympy import factorint


def verify_factors(n: int, candidate_p: int, candidate_q: int) -> bool:
    """Check whether Eve's guessed factors are actually correct."""
    return candidate_p * candidate_q == n and candidate_p > 1 and candidate_q > 1


def reference_factor(n: int) -> tuple[int, int]:
    """
    Server-side reference factoring, used for hints/scoring and for
    tests — not exposed directly to Eve's client, since showing your
    own solution defeats the point.
    """
    factors = factorint(n)
    primes = sorted(factors.keys())
    if len(primes) != 2 or any(v != 1 for v in factors.values()):
        raise ValueError("n is not a clean semiprime")
    return primes[0], primes[1]


# TODO(stretch goal): a pure-Python trial-division or Pollard's rho
# implementation Eve's own client-side "cracking" UI can call/animate
# against, separate from this server-side verifier. The server verifier
# above is the source of truth either way — a client-side factoring
# animation is cosmetic, not authoritative.
