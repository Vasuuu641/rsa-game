
import asyncio
from dataclasses import dataclass, field
from .difficulty import ROUNDS
import time


@dataclass
class PlayerState:
    player_id: str
    display_name: str
    role: str | None = None

@dataclass
class GameState:
    # 1. Mandatory fields without default values first:
    player_id: str
    session_token: str
    
    # 2. Fields with default values last:
    score: int = 0
    is_active: bool = True


@dataclass
class RoomState:
    last_attack_time: float = 0.0
    room_id: str
    players: dict[str, PlayerState] = field(default_factory=dict)
    round_number: int = 0
    status: str = "lobby"  # lobby | in_round | round_ready | match_over

    # active round's key material
    n: int | None = None
    e: int | None = None
    d: int | None = None
    owner_player_id: str | None = None  # Alice — holds d
    sender_player_id: str | None = None  # Bob — encrypts and sends

    # what Eve has to work with
    last_ciphertext: list[int] | None = None
    attempts_used: int = 0

    # match score across rounds
    defender_wins: int = 0
    eve_wins: int = 0

    # background timer task for the current round (not part of equality/repr)
    timer_task: asyncio.Task | None = field(default=None, repr=False, compare=False)


_rooms: dict[str, RoomState] = {}


def get_or_create_room(room_id: str) -> RoomState:
    if room_id not in _rooms:
        _rooms[room_id] = RoomState(room_id=room_id)
    return _rooms[room_id]


def assign_roles(room: RoomState) -> None:
    """Simple fixed assignment: first two joiners are Alice/Bob, third is Eve."""
    roles = ["alice", "bob", "eve"]
    for player, role in zip(room.players.values(), roles):
        player.role = role
        if role == "alice":
            room.owner_player_id = player.player_id
        elif role == "bob":
            room.sender_player_id = player.player_id


def get_room(room_id: str) -> RoomState | None:
    return _rooms.get(room_id)


def player_role(room: RoomState, player_id: str) -> str | None:
    player = room.players.get(player_id)
    return player.role if player else None


__all__ = [
    "PlayerState",
    "RoomState",
    "get_or_create_room",
    "assign_roles",
    "get_room",
    "player_role",
    "ROUNDS",
]
