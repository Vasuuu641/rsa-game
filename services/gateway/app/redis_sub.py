import asyncio

import redis.asyncio as redis

from .connection_manager import manager


async def redis_listener(redis_url: str) -> None:
    """
    Subscribes to every room:* channel (which also matches the private
    room:{room_id}:player:{player_id} sub-channels, since '*' spans
    colons too) and routes each message to either the whole room or a
    single player's WebSocket, based on the channel shape. Runs for the
    lifetime of the gateway process (started in main.py's startup event).
    """
    client = redis.from_url(redis_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.psubscribe("room:*")

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue
        channel: str = message["channel"]
        parts = channel.split(":")

        if len(parts) == 2:
            # "room:{room_id}" -> broadcast to everyone in the room
            room_id = parts[1]
            await manager.broadcast(room_id, message["data"])
        elif len(parts) == 4 and parts[2] == "player":
            # "room:{room_id}:player:{player_id}" -> deliver to one player
            room_id, player_id = parts[1], parts[3]
            await manager.send_to_player(room_id, player_id, message["data"])


def start_background_listener(redis_url: str) -> asyncio.Task:
    return asyncio.create_task(redis_listener(redis_url))
