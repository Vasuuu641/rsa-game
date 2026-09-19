import os
import json

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query

from .connection_manager import manager
from .redis_sub import start_background_listener

app = FastAPI(title="gateway-service")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", "http://localhost:8001")
MATCH_SERVICE_URL = os.environ.get("MATCH_SERVICE_URL", "http://localhost:8002")


@app.on_event("startup")
async def on_startup():
    start_background_listener(REDIS_URL)
    # One shared client for the life of the process, instead of a new
    # one per message — cheap fix, noted as a TODO in the original scaffold.
    app.state.http = httpx.AsyncClient()


@app.on_event("shutdown")
async def on_shutdown():
    await app.state.http.aclose()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/{room_id}")
async def room_socket(websocket: WebSocket, room_id: str, token: str = Query(...)):
    client: httpx.AsyncClient = websocket.app.state.http

    resp = await client.post(f"{AUTH_SERVICE_URL}/verify", json={"token": token})
    if resp.status_code != 200:
        await websocket.close(code=4401)
        return
    player = resp.json()

    if player.get("room_id") != room_id:
        await websocket.close(code=4403)
        return

    await manager.connect(room_id, player["player_id"], websocket)

    # Register the player with match-service as soon as the socket is up,
    # so role assignment (and the room_updated broadcast) fires the moment
    # the third player connects — the client doesn't have to ask for it.
    try:
        await client.post(
            f"{MATCH_SERVICE_URL}/rooms/join",
            json={
                "room_id": room_id,
                "player_id": player["player_id"],
                "display_name": player["display_name"],
            },
        )
    except httpx.HTTPError:
        pass  # match-service being briefly unavailable shouldn't kill the socket

    try:
        while True:
            raw = await websocket.receive_text()
            await _handle_client_message(client, room_id, player, raw)
    except WebSocketDisconnect:
        manager.disconnect(room_id, player["player_id"])


async def _handle_client_message(
    client: httpx.AsyncClient, room_id: str, player: dict, raw: str
) -> None:
    """
    Client -> server messages are plain actions; the gateway doesn't
    interpret game rules, it just forwards to match-service (the
    authoritative state machine) and lets Redis carry the resulting
    broadcast (or private message) back out.
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return

    action = msg.get("action")
    try:
        if action == "start_round":
            await client.post(
                f"{MATCH_SERVICE_URL}/rooms/start-round", json={"room_id": room_id}
            )
        elif action == "send_message":
            await client.post(
                f"{MATCH_SERVICE_URL}/rooms/send-message",
                json={"room_id": room_id, "plaintext": msg.get("plaintext", "")},
            )
        elif action == "decrypt":
            await client.post(
                f"{MATCH_SERVICE_URL}/rooms/decrypt",
                json={"room_id": room_id, "player_id": player["player_id"]},
            )
        elif action == "attack":
            await client.post(
                f"{MATCH_SERVICE_URL}/rooms/attack",
                json={
                    "room_id": room_id,
                    "candidate_p": msg["candidate_p"],
                    "candidate_q": msg["candidate_q"],
                },
            )
    except httpx.HTTPStatusError:
        # match-service rejected the action (e.g. wrong player, wrong
        # phase) — that's expected game-flow noise, not a gateway bug.
        pass
