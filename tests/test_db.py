import pytest

from cloud.db import make_session_factory, log_command, recent_commands


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
