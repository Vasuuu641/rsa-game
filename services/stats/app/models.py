import datetime

from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MatchResult(Base):
    __tablename__ = "match_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String, index=True)
    winner_role: Mapped[str] = mapped_column(String)
    round_number: Mapped[int] = mapped_column(Integer)
    key_bits: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
