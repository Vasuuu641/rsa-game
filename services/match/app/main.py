import os
import json
import asyncio

import httpx
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time

from . import state
from .difficulty import round_config, ROUNDS

app = FastAPI(title="match-service")

CRYPTO_SERVICE_URL = os.environ.get("CRYPTO_SERVICE_URL", "http://localhost:8003")
STATS_SERVICE_URL = os.environ.get("STATS_SERVICE_URL", "http://localhost:8004")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
ATTACK_COOLDOWN_SECONDS = 1.5

redis_client = redis.from_url(REDIS_URL, decode_responses=True)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/rooms/{room_id}/exists")
async def room_exists(room_id: str):
    room = state.get_room(room_id.upper())
    return {"exists": room is not None}


class JoinRoomRequest(BaseModel):
    room_id: str
    player_id: str
    display_name: str


@app.post("/rooms/join")
async def join_room(req: JoinRoomRequest):
    room = state.get_or_create_room(req.room_id)
    if req.player_id not in room.players:
        room.players[req.player_id] = state.PlayerState(
            player_id=req.player_id, display_name=req.display_name
        )

    if len(room.players) == 3 and room.status == "lobby":
        state.assign_roles(room)

    await _publish(req.room_id, {"type": "room_updated", **_players_payload(room)})
    return _players_payload(room)


class StartRoundRequest(BaseModel):
    room_id: str


@app.post("/rooms/start-round")
async def start_round(req: StartRoundRequest):
    room = state.get_room(req.room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    if len(room.players) < 3:
        raise HTTPException(status_code=400, detail="need alice, bob and eve to start")
    if room.status == "in_round":
        raise HTTPException(status_code=400, detail="round already in progress")
    if room.round_number >= len(ROUNDS):
        raise HTTPException(status_code=400, detail="match is already over")

    room.round_number += 1
    config = round_config(room.round_number)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{CRYPTO_SERVICE_URL}/keygen", json={"key_bits": config["key_bits"]}
        )
        resp.raise_for_status()
        keypair = resp.json()

    room.n = keypair["n"]
    room.e = keypair["e"]
    room.d = keypair["d"]
    room.last_ciphertext = None
    room.attempts_used = 0
    room.status = "in_round"

    # Public half goes to the whole room — Eve is *meant* to see n and e,
    # that's how real RSA works. Only d is secret.
    await _publish(
        req.room_id,
        {
            "type": "round_started",
            "round": room.round_number,
            "n": room.n,
            "e": room.e,
            "key_bits": config["key_bits"],
            "time_limit_seconds": config["time_limit_seconds"],
        },
    )

    # Private half goes only to Alice, via her own player channel.
    if room.owner_player_id:
        await _publish_to_player(
            req.room_id, room.owner_player_id, {"type": "private_key", "d": room.d}
        )

    if room.timer_task and not room.timer_task.done():
        room.timer_task.cancel()
    room.timer_task = asyncio.create_task(
        _round_timer(req.room_id, config["time_limit_seconds"])
    )

    return {"round": room.round_number, "n": room.n, "e": room.e, "key_bits": config["key_bits"]}


class SendMessageRequest(BaseModel):
    room_id: str
    plaintext: str


@app.post("/rooms/send-message")
async def send_message(req: SendMessageRequest):
    room = state.get_room(req.room_id)
    if room is None or room.status != "in_round":
        raise HTTPException(status_code=400, detail="no active round")
    if not req.plaintext.strip():
        raise HTTPException(status_code=400, detail="message is empty")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{CRYPTO_SERVICE_URL}/encrypt",
            json={"message": req.plaintext, "n": room.n, "e": room.e},
        )
        resp.raise_for_status()
        blocks = resp.json()["blocks"]

    room.last_ciphertext = blocks

    # Broadcast to the WHOLE room, deliberately — this is the moment Eve
    # "intercepts" the message. Only Alice can turn it back into text.
    await _publish(req.room_id, {"type": "ciphertext_sent", "blocks": blocks})
    return {"blocks": blocks}


class DecryptRequest(BaseModel):
    room_id: str
    player_id: str


@app.post("/rooms/decrypt")
async def decrypt(req: DecryptRequest):
    room = state.get_room(req.room_id)
    if room is None or room.status != "in_round":
        raise HTTPException(status_code=400, detail="no active round")
    if req.player_id != room.owner_player_id:
        raise HTTPException(status_code=403, detail="only Alice holds the private key")
    if not room.last_ciphertext:
        raise HTTPException(status_code=400, detail="nothing has been sent yet")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{CRYPTO_SERVICE_URL}/decrypt",
            json={"blocks": room.last_ciphertext, "n": room.n, "d": room.d},
        )
        resp.raise_for_status()
        plaintext = resp.json()["message"]

    await _publish_to_player(
        req.room_id, req.player_id, {"type": "message_decrypted", "plaintext": plaintext}
    )
    return {"plaintext": plaintext}


class AttackRequest(BaseModel):
    room_id: str
    candidate_p: int
    candidate_q: int


@app.post("/rooms/attack")
async def attack(req: AttackRequest):
    room = state.get_room(req.room_id)
    if room is None or room.n is None or room.status != "in_round":
        raise HTTPException(status_code=404, detail="room not in an active round")

    # Rate limiting / cooldown check per room
    now = time.time()
    elapsed = now - room.last_attack_time
    if elapsed < ATTACK_COOLDOWN_SECONDS:
        remaining_wait = round(ATTACK_COOLDOWN_SECONDS - elapsed, 1)
        raise HTTPException(
            status_code=429,
            detail=f"Attack on cooldown. Please wait {remaining_wait}s before trying again.",
        )

    # Update cooldown timestamp and increment counter
    room.last_attack_time = now
    room.attempts_used += 1

    # Send factor candidates to crypto-service for verification and decryption
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{CRYPTO_SERVICE_URL}/crack",
            json={
                "n": room.n,
                "e": room.e,
                "candidate_p": req.candidate_p,
                "candidate_q": req.candidate_q,
                "blocks": room.last_ciphertext or [],
            },
        )
        resp.raise_for_status()
        data = resp.json()

    correct = data["correct"]

    # Broadcast attack result to all clients connected via WebSocket/Redis pubsub
    await _publish(
        req.room_id,
        {
            "type": "attack_result",
            "correct": correct,
            "attempts_used": room.attempts_used,
            "plaintext": data.get("plaintext"),
        },
    )

    # If Eve guessed correctly, end round and grant point
    if correct:
        if room.timer_task and not room.timer_task.done():
            room.timer_task.cancel()
        room.eve_wins += 1
        room.status = "round_ready"
        await _finish_round(req.room_id, winner="eve")

    return {
        "correct": correct,
        "attempts_used": room.attempts_used,
        "plaintext": data.get("plaintext"),
    }

async def _round_timer(room_id: str, seconds: int) -> None:
    remaining = seconds
    try:
        while remaining > 0:
            step = min(5, remaining)
            await asyncio.sleep(step)
            remaining -= step
            room = state.get_room(room_id)
            if room is None or room.status != "in_round":
                return  # round already ended (Eve cracked it, etc.)
            await _publish(room_id, {"type": "round_timer", "seconds_remaining": remaining})

        room = state.get_room(room_id)
        if room and room.status == "in_round":
            room.status = "round_ready"
            room.defender_wins += 1
            await _publish(
                room_id,
                {
                    "type": "attack_result",
                    "correct": False,
                    "attempts_used": room.attempts_used,
                    "timeout": True,
                },
            )
            await _finish_round(room_id, winner="alice_bob")
    except asyncio.CancelledError:
        return


async def _finish_round(room_id: str, winner: str) -> None:
    room = state.get_room(room_id)
    if room is None:
        return

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{STATS_SERVICE_URL}/results",
                json={
                    "room_id": room_id,
                    "winner_role": winner,
                    "round_number": room.round_number,
                    "key_bits": room.n.bit_length() if room.n else 0,
                },
                timeout=5.0,
            )
        except httpx.HTTPError:
            pass  # stats is best-effort; don't block gameplay if it's down

    if room.round_number >= len(ROUNDS):
        room.status = "match_over"
        overall = "eve" if room.eve_wins > room.defender_wins else "alice_bob"
        await _publish(
            room_id,
            {
                "type": "match_over",
                "winner": overall,
                "eve_wins": room.eve_wins,
                "defender_wins": room.defender_wins,
            },
        )
    else:
        await _publish(room_id, {"type": "round_ready", "next_round": room.round_number + 1})


def _players_payload(room: state.RoomState) -> dict:
    return {
        "room_id": room.room_id,
        "status": room.status,
        "defender_wins": room.defender_wins,
        "eve_wins": room.eve_wins,
        "players": [
            {"player_id": p.player_id, "display_name": p.display_name, "role": p.role}
            for p in room.players.values()
        ],
    }


async def _publish(room_id: str, payload: dict) -> None:
    await redis_client.publish(f"room:{room_id}", json.dumps(payload))


async def _publish_to_player(room_id: str, player_id: str, payload: dict) -> None:
    await redis_client.publish(f"room:{room_id}:player:{player_id}", json.dumps(payload))
