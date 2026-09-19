"""
The one fixed difficulty curve for the game (per the scope decision —
no adjustable difficulty for this version). Three rounds, each with a
larger key size and a longer clock, so Eve's factoring gets harder
while Alice/Bob's window to communicate grows to compensate.
"""

ROUNDS = [
    {"round": 1, "key_bits": 16, "time_limit_seconds": 60},
    {"round": 2, "key_bits": 24, "time_limit_seconds": 90},
    {"round": 3, "key_bits": 32, "time_limit_seconds": 120},
]


def round_config(round_number: int) -> dict:
    for r in ROUNDS:
        if r["round"] == round_number:
            return r
    raise ValueError(f"no config for round {round_number}")
