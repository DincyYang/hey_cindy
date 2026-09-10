import fakeredis
import pytest
from fastapi.testclient import TestClient

import cloud.app as app_module
from cloud.db import make_session_factory
from cloud.state import LightState

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    # The token is read into a module global at import time, which may have
    # happened before conftest set the env var — pin it explicitly.
    monkeypatch.setattr(app_module, "API_TOKEN", "test-token")
    # Swap both stores for local stand-ins: fakeredis and a per-test SQLite file.
    monkeypatch.setattr(app_module, "light", LightState(
        client=fakeredis.FakeStrictRedis(decode_responses=True)))
    monkeypatch.setattr(app_module, "session_factory",
                        make_session_factory(f"sqlite:///{tmp_path}/api.db"))
    return TestClient(app_module.app)


def test_requires_token(client):
    assert client.get("/state").status_code == 401
    assert client.get("/metrics").status_code == 401
    assert client.post("/command", json={"command": "on"}).status_code == 401


def test_rejects_unknown_command(client):
    r = client.post("/command", json={"command": "blink"}, headers=AUTH)
    assert r.status_code == 400


def test_command_updates_state_and_history(client):
    r = client.post("/command", headers=AUTH, json={
        "command": "on", "raw_text": "turn on the light", "confidence": 0.95,
        "reason": "keyword match: on", "latency_ms": 3.4,
        "input_tokens": 0, "output_tokens": 0,
    })
    assert r.status_code == 200

    state = client.get("/state", headers=AUTH).json()
    assert state["light"] == "on"
    assert state["count"] == 1
    row = state["history"][-1]
    assert row["normalized"] == "on"
    assert row["latency_ms"] == 3.4


def test_metrics_aggregate_latency_and_cost(client):
    # One keyword-path command (no tokens) and one LLM-path command.
    client.post("/command", headers=AUTH, json={
        "command": "on", "latency_ms": 4.0, "input_tokens": 0, "output_tokens": 0})
    client.post("/command", headers=AUTH, json={
        "command": "off", "latency_ms": 600.0,
        "input_tokens": 200_000, "output_tokens": 100_000})

    m = client.get("/metrics", headers=AUTH).json()
    assert m["commands"] == 2
    assert m["llm_calls"] == 1
    assert m["llm_share"] == 0.5
    assert m["avg_latency_ms"] == 302.0
    assert m["p95_latency_ms"] == 600.0
    # 0.2M input @ $1/M + 0.1M output @ $5/M = $0.70
    assert m["cost_usd"] == pytest.approx(0.70)


def test_health_needs_no_token(client):
    assert client.get("/health").json()["status"] == "ok"
