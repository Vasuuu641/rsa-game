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


def trial_division(n: int) -> tuple[int, int] | None:
    """
    Pure Python trial division suitable for animation or demonstration
    at gameplay key-size scales (16–32 bits).
    """
    if n % 2 == 0:
        return 2, n // 2
    d = 3
    while d * d <= n:
        if n % d == 0:
            return d, n // d
        d += 2
    return None