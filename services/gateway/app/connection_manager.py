from fastapi import WebSocket


class ConnectionManager:
    """Tracks live WebSocket connections per room_id AND per player_id
    within that room, so events can be broadcast to everyone in a room
    (e.g. a public key) or delivered privately to one player (e.g. the
    private key, or a decrypted message)."""

    def __init__(self) -> None:
        self._rooms: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, room_id: str, player_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._rooms.setdefault(room_id, {})[player_id] = ws

    def disconnect(self, room_id: str, player_id: str) -> None:
        conns = self._rooms.get(room_id)
        if conns:
            conns.pop(player_id, None)
            if not conns:
                self._rooms.pop(room_id, None)

    async def broadcast(self, room_id: str, message: str) -> None:
        for player_id, ws in list(self._rooms.get(room_id, {}).items()):
            try:
                await ws.send_text(message)
            except Exception:
                # connection likely already gone — clean it up
                self.disconnect(room_id, player_id)

    async def send_to_player(self, room_id: str, player_id: str, message: str) -> None:
        ws = self._rooms.get(room_id, {}).get(player_id)
        if ws is None:
            return
        try:
            await ws.send_text(message)
        except Exception:
            self.disconnect(room_id, player_id)


manager = ConnectionManager()
