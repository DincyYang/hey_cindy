import pytest
from sqlalchemy import create_engine, inspect, text

from cloud.db import (
    make_session_factory, log_command, recent_commands, usage_summary,
    estimate_cost_usd, _ensure_columns,
)


@pytest.fixture
def session_factory(tmp_path):
    # Real SQLite file (per-test) stands in for Postgres — same SQLAlchemy code path.
    return make_session_factory(f"sqlite:///{tmp_path}/test.db")


def test_log_then_read(session_factory):
    log_command(session_factory, command="on", raw_text="turn on", source="voice")
    log_command(session_factory, command="off", raw_text="turn off", source="dashboard")

    rows = recent_commands(session_factory)
    assert len(rows) == 2
    assert rows[-1]["normalized"] == "off"
    assert rows[-1]["raw"] == "turn off"


def test_recent_respects_limit(session_factory):
    for _ in range(15):
        log_command(session_factory, command="on")
    assert len(recent_commands(session_factory, limit=10)) == 10


def test_read_on_broken_db_returns_empty():
    # Point at an unreachable Postgres; reads degrade to [] instead of raising.
    sf = make_session_factory("postgresql+psycopg2://x:x@127.0.0.1:1/nope")
    assert recent_commands(sf) == []


def test_metrics_round_trip(session_factory):
    log_command(session_factory, command="on", raw_text="turn on",
                latency_ms=412.5, input_tokens=180, output_tokens=42)
    row = recent_commands(session_factory)[-1]
    assert row["latency_ms"] == 412.5
    assert row["input_tokens"] == 180
    assert row["output_tokens"] == 42
    # 180 in @ $1/M + 42 out @ $5/M
    assert row["cost_usd"] == pytest.approx(180 / 1e6 + 42 * 5 / 1e6)


def test_estimate_cost_handles_missing_tokens():
    assert estimate_cost_usd(None, None) == 0.0
    assert estimate_cost_usd(1_000_000, 1_000_000) == pytest.approx(6.00)


def test_usage_summary_empty(session_factory):
    summary = usage_summary(session_factory)
    assert summary["commands"] == 0
    assert summary["cost_usd"] == 0.0


def test_usage_summary_ignores_rows_without_latency(session_factory):
    # A dashboard command runs no NLP, so it has no latency to average in.
    log_command(session_factory, command="on", source="dashboard")
    log_command(session_factory, command="off", source="voice",
                latency_ms=100.0, input_tokens=10, output_tokens=5)

    summary = usage_summary(session_factory)
    assert summary["commands"] == 2
    assert summary["llm_calls"] == 1
    assert summary["avg_latency_ms"] == 100.0


def test_usage_summary_on_broken_db_returns_zeros():
    sf = make_session_factory("postgresql+psycopg2://x:x@127.0.0.1:1/nope")
    assert usage_summary(sf)["commands"] == 0


def test_ensure_columns_adds_metrics_to_an_old_table(tmp_path):
    """A database created before instrumentation shipped gets the new columns."""
    url = f"sqlite:///{tmp_path}/legacy.db"
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE command_logs ("
            "id INTEGER PRIMARY KEY, command VARCHAR(10), raw_text VARCHAR(500), "
            "source VARCHAR(20), confidence FLOAT, reason VARCHAR(50), created_at DATETIME)"
        ))

    sf = make_session_factory(url)          # runs create_all + _ensure_columns
    columns = {c["name"] for c in inspect(engine).get_columns("command_logs")}
    assert {"latency_ms", "input_tokens", "output_tokens"} <= columns

    log_command(sf, command="on", latency_ms=5.0, input_tokens=1, output_tokens=1)
    assert recent_commands(sf)[-1]["latency_ms"] == 5.0


def test_write_on_broken_db_does_not_raise():
    """The resilience claim: a dead Postgres must not fail a command that has
    already taken effect in Redis."""
    sf = make_session_factory("postgresql+psycopg2://x:x@127.0.0.1:1/nope")
    log_command(sf, command="on", raw_text="turn on", latency_ms=1.0)  # must not raise


def test_ensure_columns_is_a_noop_without_the_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/empty.db")
    _ensure_columns(engine)  # nothing to migrate yet
    assert not inspect(engine).has_table("command_logs")
