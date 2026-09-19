import os
import uuid
import random
import string
import datetime

import httpx
import jwt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="auth-service")

# The web client is a static page opened from a different origin/port than
# this API, so it needs CORS. Wide open here since there are no user
# accounts or cookies to protect for a class project.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
MATCH_SERVICE_URL = os.environ.get("MATCH_SERVICE_URL", "http://localhost:8000")

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"
TOKEN_TTL_MINUTES = 60


@app.get("/health")
async def health():
    return {"status": "ok"}


class JoinRequest(BaseModel):
    display_name: str
    room_id: str | None = None  # omit to create a new room


class JoinResponse(BaseModel):
    player_id: str
    room_id: str
    token: str


@app.post("/join", response_model=JoinResponse)
async def join(req: JoinRequest):
    if not req.display_name.strip():
        raise HTTPException(status_code=400, detail="display_name is required")

    player_id = str(uuid.uuid4())
    room_id = (req.room_id or await _generate_unique_room_code()).strip().upper()

    payload = {
        "player_id": player_id,
        "room_id": room_id,
        "display_name": req.display_name,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=TOKEN_TTL_MINUTES),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

    return JoinResponse(player_id=player_id, room_id=room_id, token=token)


class VerifyRequest(BaseModel):
    token: str


@app.post("/verify")
async def verify(req: VerifyRequest):
    try:
        payload = jwt.decode(req.token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return payload


def _generate_room_code(length: int = 4) -> str:
    return "".join(random.choices(string.ascii_uppercase, k=length))


async def _generate_unique_room_code(max_attempts: int = 10) -> str:
    """Generates a random room code and checks match-service to ensure no collision."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        for _ in range(max_attempts):
            code = _generate_room_code()
            try:
                res = await client.get(f"{MATCH_SERVICE_URL}/rooms/{code}/exists")
                if res.status_code == 200 and not res.json().get("exists", False):
                    return code
            except httpx.RequestError:
                # Fallback if match-service is offline during standalone auth testing
                return code

    raise HTTPException(status_code=500, detail="Unable to generate unique room code")