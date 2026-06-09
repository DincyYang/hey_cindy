# cloud/db.py
"""Command history lives in PostgreSQL (durable, queryable for analytics).

Writing history is a NON-critical path: if Postgres is down, the command has
already taken effect (state went to Redis), so we log the error and move on
rather than failing the request. Reads degrade to an empty list.

No Alembic on purpose — at this scale `create_all` is enough; a migration tool
would be over-engineering.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg2://cindy:cindy@localhost:5432/hey_cindy"
)

Base = declarative_base()


class CommandLog(Base):
    __tablename__ = "command_logs"
    id = Column(Integer, primary_key=True, index=True)
    command = Column(String(10))
    raw_text = Column(String(500), nullable=True)
    source = Column(String(20), default="voice")
    confidence = Column(Float, nullable=True)
    reason = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def make_session_factory(database_url: str = DATABASE_URL, **engine_kwargs):
    """Build a session factory. Tolerant of a dead DB at startup so the API can
    still boot and serve the (Redis-backed) light state."""
    engine = create_engine(database_url, **engine_kwargs)
    try:
        Base.metadata.create_all(engine)
    except Exception as e:
        logger.error("Could not create tables at startup (%s); will retry on use", e)
    return sessionmaker(bind=engine)


def log_command(
    session_factory,
    *,
    command: str,
    raw_text: Optional[str] = None,
    source: str = "voice",
    confidence: Optional[float] = None,
    reason: Optional[str] = None,
) -> None:
    try:
        with session_factory() as session:
            session.add(CommandLog(
                command=command, raw_text=raw_text, source=source,
                confidence=confidence, reason=reason,
            ))
            session.commit()
    except Exception as e:
        logger.error("Failed to write command history (%s); command still executed", e)


def recent_commands(session_factory, limit: int = 10) -> list[dict]:
    try:
        with session_factory() as session:
            rows = (
                session.query(CommandLog)
                .order_by(CommandLog.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {"timestamp": str(r.created_at), "raw": r.raw_text, "normalized": r.command}
                for r in reversed(rows)
            ]
    except Exception as e:
        logger.error("Failed to read command history (%s); returning empty", e)
        return []
