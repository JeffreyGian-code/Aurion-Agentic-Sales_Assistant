from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import chat_usage
from app.api.dependencies import get_agent
from app.api.main import app
from app.api.rate_limit import limiter
from app.tests.test_api import FakeAgent
from app.tests.test_chat_stream import StreamAgent, frames


def test_reset_changes_context_but_preserves_budget_across_routes():
    limiter.reset()
    agent = FakeAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    try:
        client = TestClient(app)
        session = client.post('/api/chat', json={'message': 'Remember Honda'}).json()['session_id']
        original_thread = agent.calls[0][1]['configurable']['thread_id']
        stream_agent = StreamAgent()
        app.dependency_overrides[get_agent] = lambda: stream_agent
        response = client.post('/api/chat/stream', json={'message': 'Start fresh', 'session_id': session, 'reset_context': True})
        assert frames(response)[-1][0] == 'completed'
        fresh_thread = stream_agent.calls[0][1]['configurable']['thread_id']
        assert fresh_thread != original_thread
        assert client.get(f'/api/chat/usage/{session}').json()['calls'] == 2
        app.dependency_overrides[get_agent] = lambda: agent
        client.post('/api/chat', json={'message': 'Continue', 'session_id': session})
        assert agent.calls[-1][1]['configurable']['thread_id'] == fresh_thread
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def test_budget_blocks_reset_until_24_hours(monkeypatch):
    now = 1000
    monkeypatch.setattr(chat_usage.time, 'time', lambda: now)
    for count in range(1, 8):
        usage = chat_usage.session_usage('user', consume=True, reset_context=True)
        assert usage['calls'] == count
        assert usage['resets_at'] == 87400
    with pytest.raises(HTTPException) as error:
        chat_usage.session_usage('user', consume=True, reset_context=True)
    assert error.value.status_code == 429
    assert chat_usage.session_usage('other', consume=True)['calls'] == 1
    now = 87400
    assert chat_usage.session_usage('user')['calls'] == 0
    assert chat_usage.session_usage('user', consume=True)['calls'] == 1


def test_dev_chat_can_continue_after_seven_calls(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    limiter.reset()
    agent = FakeAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    try:
        with TestClient(app) as client:
            first = client.post("/api/chat", json={"message": "Find cars"})
            session = first.json()["session_id"]
            for _ in range(6):
                assert client.post("/api/chat", json={
                    "message": "Continue", "session_id": session,
                }).status_code == 200

            stream_agent = StreamAgent()
            app.dependency_overrides[get_agent] = lambda: stream_agent
            response = client.post("/api/chat/stream", json={
                "message": "Start fresh", "session_id": session, "reset_context": True,
            })
            assert frames(response)[-1][0] == "completed"
            assert stream_agent.calls[0][1]["configurable"]["thread_id"] != session
            assert client.get(f"/api/chat/usage/{session}").json() == {
                "calls": 0, "limit": None, "resets_at": None,
            }
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def test_concurrent_requests_cannot_overspend():
    def call(_):
        try:
            chat_usage.session_usage('concurrent', consume=True)
            return True
        except HTTPException:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(call, range(12))) == 7
    assert chat_usage.session_usage('concurrent')['calls'] == 7


def test_session_ownership_and_replay_across_routes():
    limiter.reset()
    agent = FakeAgent()
    app.dependency_overrides[get_agent] = lambda: agent
    try:
        with TestClient(app) as client, TestClient(app) as stranger:
            data = {"message": "cars", "request_id": "one"}
            original = client.post("/api/chat", json=data).json()
            session = original["session_id"]
            assert stranger.get(f"/api/chat/usage/{session}").status_code == 404
            assert stranger.post("/api/chat", json={**data, "session_id": session}).status_code == 404
            assert frames(client.post("/api/chat/stream", json=data))[-1] == ("completed", original)
            assert len(agent.calls) == 1
            assert client.get(f"/api/chat/usage/{session}").json()["calls"] == 1
            assert client.post("/api/chat", json={**data, "message": "changed"}).status_code == 409
    finally:
        app.dependency_overrides.clear()
        limiter.reset()


def test_failed_turn_and_overlapping_turn_preserve_committed_history():
    session, lease, _, _, _, owner = chat_usage.begin(None, "first", False, "first", None)
    history = [{"type": "human", "data": {"content": "first"}}]
    chat_usage.finish(session, lease, "first", history, "done")
    _, lease, before, *_ = chat_usage.begin(session, "next", False, "second", owner)
    with pytest.raises(HTTPException) as busy:
        chat_usage.begin(session, "overlap", False, "other", owner)
    assert busy.value.status_code == 409
    chat_usage.finish(session, lease, "second")
    _, _, after, *_ = chat_usage.begin(session, "next", False, "second", owner)
    assert before == after == history
    assert chat_usage.owned_usage(session, owner)["calls"] == 2


def test_stale_id_recovery_restores_cookie_owner_and_budget():
    session, lease, *_rest, owner = chat_usage.begin(None, "first", False, "first", None)
    chat_usage.finish(session, lease, "first", [], "done")
    with pytest.raises(HTTPException) as expired:
        chat_usage.begin("stale-session", "next", False, "next", owner)
    assert expired.value.status_code == 404
    assert expired.value.headers["X-Error-Code"] == "session-expired"
    recovered, lease, *_ = chat_usage.begin(None, "next", False, "next", owner)
    assert recovered == session
    assert chat_usage.owned_usage(session, owner)["calls"] == 2
    chat_usage.finish(session, lease, "next", [], "done")


def test_lost_cookie_recovery_never_exposes_previous_history():
    session, lease, *_rest, owner = chat_usage.begin(None, "private", False, "first", None)
    chat_usage.finish(session, lease, "first", [{"private": "history"}], "done")
    with pytest.raises(HTTPException):
        chat_usage.begin(session, "next", False, "next", None)
    recovered, _, history, _, _, new_owner = chat_usage.begin(None, "next", False, "next", None)
    assert recovered != session
    assert new_owner != owner
    assert history == []
    assert chat_usage.owned_usage(session, owner)["calls"] == 1
