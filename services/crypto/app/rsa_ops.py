"""
RSA operations at gameplay-scale key sizes (16-64 bits).

NOTE: the `cryptography` library refuses to generate keys below ~512
bits (correctly, for real use) so it's not usable for the deliberately
crackable keys this game needs. This module implements textbook RSA
directly using sympy for prime generation — fine for a game where the
whole point is that small keys ARE breakable, not fine for anything
handling real secrets. Don't reuse this module outside this project.
"""

from sympy import randprime, gcd, mod_inverse


def _random_prime(bits: int) -> int:
    low = 2 ** (bits - 1)
    high = 2**bits - 1
    return randprime(low, high)


def generate_keypair(key_bits: int) -> dict:
    """
    Generate an RSA keypair where n has approximately key_bits bits
    (p and q each roughly key_bits // 2 bits).
    """
    half = max(key_bits // 2, 4)
    while True:
        p = _random_prime(half)
        q = _random_prime(half)
        if p == q:
            continue
        n = p * q
        phi = (p - 1) * (q - 1)
        e = 65537 if 65537 < phi and gcd(65537, phi) == 1 else 17
        if gcd(e, phi) != 1:
            continue
        d = mod_inverse(e, phi)
        return {"n": n, "e": e, "d": d, "p": p, "q": q, "key_bits": n.bit_length()}


def derive_private_key(p: int, q: int, e: int) -> int:
    """Given the (correct) prime factors of n and the public exponent,
    recompute the private exponent — this is exactly what Eve is doing
    when she "breaks" the key."""
    phi = (p - 1) * (q - 1)
    return mod_inverse(e, phi)


def encrypt_block(m: int, n: int, e: int) -> int:
    if m >= n:
        raise ValueError("message block too large for this key size")
    return pow(m, e, n)


def decrypt_block(c: int, n: int, d: int) -> int:
    return pow(c, d, n)


def text_to_blocks(text: str, n: int) -> list[int]:
    """Chunk text into integer blocks small enough to fit under n."""
    max_bytes = max((n.bit_length() - 1) // 8, 1)
    data = text.encode("utf-8")
    return [
        int.from_bytes(data[i : i + max_bytes], "big")
        for i in range(0, len(data), max_bytes)
    ]


def blocks_to_text(blocks: list[int]) -> str:
    out = bytearray()
    for b in blocks:
        length = max((b.bit_length() + 7) // 8, 1)
        out += b.to_bytes(length, "big")
    return out.decode("utf-8", errors="replace")
