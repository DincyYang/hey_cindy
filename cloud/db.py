"""Command history lives in PostgreSQL (durable, queryable for analytics).

Writing history is a NON-critical path: if Postgres is down, the command has
already taken effect (state went to Redis), so we log the error and move on
rather than failing the request. Reads degrade to an empty list.

Every row also carries the per-command latency and Claude token usage measured
by the local pipeline, which is what makes `usage_summary()` — and the cost /
latency panel on the dashboard — possible.

No Alembic on purpose — at this scale `create_all` plus the additive column
check in `_ensure_columns` is enough; a migration tool would be over-engineering.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    create_engine, inspect, text, Column, Integer, String, Float, DateTime,
)
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg2://cindy:cindy@localhost:5432/hey_cindy"
)

# Claude Haiku 4.5 list price, USD per million tokens. Override per deployment
# if the classifier model changes. Cost is derived here and nowhere else.
PRICE_IN_PER_MTOK = float(os.environ.get("HEY_CINDY_PRICE_IN", "1.00"))
PRICE_OUT_PER_MTOK = float(os.environ.get("HEY_CINDY_PRICE_OUT", "5.00"))

Base = declarative_base()


class CommandLog(Base):
    __tablename__ = "command_logs"
    id = Column(Integer, primary_key=True, index=True)
    command = Column(String(10))
    raw_text = Column(String(500), nullable=True)
    source = Column(String(20), default="voice")
    confidence = Column(Float, nullable=True)
    reason = Column(String(50), nullable=True)
    # Instrumentation, nullable because non-voice sources (the dashboard) run
    # no NLP and therefore have nothing to report.
    latency_ms = Column(Float, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Token counts -> dollars. The single place pricing is applied."""
    return (
        (input_tokens or 0) / 1_000_000 * PRICE_IN_PER_MTOK
        + (output_tokens or 0) / 1_000_000 * PRICE_OUT_PER_MTOK
    )


# Columns added after the table first shipped. `create_all` only creates missing
# tables, so an already-deployed database needs them added explicitly.
_ADDED_COLUMNS = {
    "latency_ms": "FLOAT",
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
}


def _ensure_columns(engine) -> None:
    """Additive, idempotent mini-migration for an existing command_logs table."""
    inspector = inspect(engine)
    if not inspector.has_table(CommandLog.__tablename__):
        return  # create_all just made it with the full schema

    existing = {c["name"] for c in inspector.get_columns(CommandLog.__tablename__)}
    missing = {n: t for n, t in _ADDED_COLUMNS.items() if n not in existing}
    if not missing:
        return

    with engine.begin() as conn:
        for name, sql_type in missing.items():
            # ALTER TABLE ... ADD COLUMN is supported by both SQLite and Postgres.
            conn.execute(text(
                f"ALTER TABLE {CommandLog.__tablename__} ADD COLUMN {name} {sql_type}"
            ))
    logger.info("Added missing command_logs columns: %s", ", ".join(missing))


def make_session_factory(database_url: str = DATABASE_URL, **engine_kwargs):
    """Build a session factory. Tolerant of a dead DB at startup so the API can
    still boot and serve the (Redis-backed) light state."""
    engine = create_engine(database_url, **engine_kwargs)
    try:
        Base.metadata.create_all(engine)
        _ensure_columns(engine)
    except Exception as e:
        logger.error("Could not prepare schema at startup (%s); will retry on use", e)
    return sessionmaker(bind=engine)


def log_command(
    session_factory,
    *,
    command: str,
    raw_text: Optional[str] = None,
    source: str = "voice",
    confidence: Optional[float] = None,
    reason: Optional[str] = None,
    latency_ms: Optional[float] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
) -> None:
    try:
        with session_factory() as session:
            session.add(CommandLog(
                command=command, raw_text=raw_text, source=source,
                confidence=confidence, reason=reason,
                latency_ms=latency_ms,
                input_tokens=input_tokens, output_tokens=output_tokens,
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
                {
                    "timestamp": str(r.created_at),
                    "raw": r.raw_text,
                    "normalized": r.command,
                    "source": r.source,
                    "latency_ms": r.latency_ms,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "cost_usd": estimate_cost_usd(r.input_tokens, r.output_tokens),
                }
                for r in reversed(rows)
            ]
    except Exception as e:
        logger.error("Failed to read command history (%s); returning empty", e)
        return []


def usage_summary(session_factory, limit: int = 200) -> dict:
    """Aggregate cost/performance over the most recent `limit` commands.

    Percentiles are computed in Python over a bounded window rather than in SQL:
    the window is small, and it keeps the query portable across SQLite (tests)
    and Postgres (production).
    """
    empty = {
        "commands": 0, "llm_calls": 0, "llm_share": 0.0,
        "avg_latency_ms": 0.0, "p95_latency_ms": 0.0,
        "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
    }
    try:
        with session_factory() as session:
            rows = (
                session.query(CommandLog)
                .order_by(CommandLog.created_at.desc())
                .limit(limit)
                .all()
            )
    except Exception as e:
        logger.error("Failed to read usage summary (%s); returning zeros", e)
        return empty

    if not rows:
        return empty

    latencies = sorted(r.latency_ms for r in rows if r.latency_ms is not None)
    in_tok = sum(r.input_tokens or 0 for r in rows)
    out_tok = sum(r.output_tokens or 0 for r in rows)
    llm_calls = sum(1 for r in rows if (r.input_tokens or 0) > 0)

    p95 = 0.0
    if latencies:
        # Nearest-rank p95; with a handful of samples this is the last element.
        idx = max(0, min(len(latencies) - 1, round(0.95 * len(latencies)) - 1))
        p95 = latencies[idx]

    return {
        "commands": len(rows),
        "llm_calls": llm_calls,
        "llm_share": round(llm_calls / len(rows), 3),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": round(p95, 2),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": round(estimate_cost_usd(in_tok, out_tok), 6),
    }
