import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from .models import Base, MatchResult

app = FastAPI(title="stats-service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://rsagame:rsagame@localhost/rsagame"
)
engine = create_async_engine(DATABASE_URL)


@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/health")
async def health():
    return {"status": "ok"}


class RecordResultRequest(BaseModel):
    room_id: str
    winner_role: str
    round_number: int
    key_bits: int


@app.post("/results")
async def record_result(req: RecordResultRequest):
    async with AsyncSession(engine) as session:
        result = MatchResult(
            room_id=req.room_id,
            winner_role=req.winner_role,
            round_number=req.round_number,
            key_bits=req.key_bits,
        )
        session.add(result)
        await session.commit()
    return {"status": "recorded"}


@app.get("/leaderboard")
async def leaderboard():
    async with AsyncSession(engine) as session:
        stmt = (
            select(MatchResult.winner_role, func.count().label("wins"))
            .group_by(MatchResult.winner_role)
            .order_by(func.count().desc())
        )
        rows = (await session.execute(stmt)).all()
    return [{"role": role, "wins": wins} for role, wins in rows]


# TODO: pagination on a /results list endpoint once you have more than a
# handful of rows — not needed for a class demo dataset.
