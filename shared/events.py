"""
Reference for the WebSocket event shapes flowing gateway -> client, and
the action shapes flowing client -> gateway -> match-service.

Not a package that gets pip-installed across services (that's overkill
for a class project) — services build these as plain dicts. Kept here
as the single source of truth for the shapes so they stay consistent
while services are built/changed independently.
"""

from enum import StrEnum
from pydantic import BaseModel


class Role(StrEnum):
    ALICE = "alice"
    BOB = "bob"
    EVE = "eve"


class ClientAction(StrEnum):
    START_ROUND = "start_round"
    SEND_MESSAGE = "send_message"
    DECRYPT = "decrypt"
    ATTACK = "attack"


class EventType(StrEnum):
    ROOM_UPDATED = "room_updated"        # broadcast: roster + roles + score
    ROUND_STARTED = "round_started"      # broadcast: public key (n, e) + timer
    PRIVATE_KEY = "private_key"          # private to Alice: d
    CIPHERTEXT_SENT = "ciphertext_sent"  # broadcast: Bob's encrypted message
    MESSAGE_DECRYPTED = "message_decrypted"  # private to Alice: plaintext
    ATTACK_RESULT = "attack_result"      # broadcast: correct/incorrect (+ plaintext if Eve won)
    ROUND_TIMER = "round_timer"          # broadcast: seconds_remaining, every 5s
    ROUND_READY = "round_ready"          # broadcast: round over, waiting for next start_round
    MATCH_OVER = "match_over"            # broadcast: overall winner after round 3


# --- Example payload shapes (informal — actual code sends plain dicts) ---


class RoomUpdated(BaseModel):
    type: EventType = EventType.ROOM_UPDATED
    room_id: str
    status: str
    defender_wins: int
    eve_wins: int
    players: list[dict]  # [{player_id, display_name, role}]


class RoundStarted(BaseModel):
    type: EventType = EventType.ROUND_STARTED
    round: int
    n: int
    e: int
    key_bits: int
    time_limit_seconds: int


class PrivateKey(BaseModel):
    type: EventType = EventType.PRIVATE_KEY
    d: int


class CiphertextSent(BaseModel):
    type: EventType = EventType.CIPHERTEXT_SENT
    blocks: list[int]


class MessageDecrypted(BaseModel):
    type: EventType = EventType.MESSAGE_DECRYPTED
    plaintext: str


class AttackResult(BaseModel):
    type: EventType = EventType.ATTACK_RESULT
    correct: bool
    attempts_used: int
    plaintext: str | None = None
    timeout: bool = False


class RoundTimer(BaseModel):
    type: EventType = EventType.ROUND_TIMER
    seconds_remaining: int


class MatchOver(BaseModel):
    type: EventType = EventType.MATCH_OVER
    winner: str  # "alice_bob" | "eve"
    eve_wins: int
    defender_wins: int
