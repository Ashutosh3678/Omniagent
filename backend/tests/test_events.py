from __future__ import annotations

import asyncio
import threading
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_api import _register, _signup, _ws

from app import auth, hub as hub_module
from app.hub import MAX_SUBSCRIBERS_PER_USER, RESYNC, Hub, Subscriber
from app.main import app
from app.ratelimit import pairing_limiter, planner_limiter
from app.routers import events as events_router
from app.store import store


def setup_function() -> None:
    store.reset()
    pairing_limiter.reset()
    planner_limiter.reset()


def token_of(user: dict) -> str:
    return user["Authorization"].split(" ", 1)[1]


def listen(client: TestClient, user: dict):
    """Opens the live stream the way the phone does: connect, then authenticate in the first message."""
    ws = client.websocket_connect("/api/v1/events")
    return ws


def authed(ws, user: dict) -> dict:
    ws.send_json({"type": "auth", "token": token_of(user)})
    return ws.receive_json()


# --- the hub on its own
def test_events_reach_only_their_own_user() -> None:
    async def go():
        hub = Hub()
        loop = asyncio.get_running_loop()
        alice, bob = hub.subscribe("alice", loop), hub.subscribe("bob", loop)
        hub.publish("alice", {"type": "task", "task": {"id": "1"}})
        await asyncio.sleep(0.05)
        assert alice.queue.qsize() == 1 and bob.queue.qsize() == 0
        assert (await alice.queue.get())["task"]["id"] == "1"

    asyncio.run(go())


def test_publishing_from_another_thread_is_safe() -> None:
    async def go():
        hub = Hub()
        sub = hub.subscribe("alice", asyncio.get_running_loop())
        threading.Thread(target=lambda: hub.publish("alice", {"n": 1})).start()
        assert await asyncio.wait_for(sub.queue.get(), 2) == {"n": 1}

    asyncio.run(go())


def test_a_phone_that_stops_reading_gets_a_resync_not_a_pile_of_stale_events() -> None:
    async def go():
        sub = Subscriber("alice", asyncio.get_running_loop())
        for n in range(hub_module.QUEUE_SIZE):
            sub.put({"n": n})
        sub.put({"n": "one too many"})
        assert sub.queue.qsize() == 1 and sub.queue.get_nowait() == RESYNC

    asyncio.run(go())


def test_the_connection_limit_per_user() -> None:
    async def go():
        hub = Hub()
        loop = asyncio.get_running_loop()
        subs = [hub.subscribe("alice", loop) for _ in range(MAX_SUBSCRIBERS_PER_USER)]
        assert all(subs) and hub.subscribe("alice", loop) is None
        assert hub.subscribe("bob", loop) is not None
        hub.unsubscribe(subs[0])
        assert hub.subscribe("alice", loop) is not None

    asyncio.run(go())


def test_a_closed_phone_is_dropped_instead_of_raising() -> None:
    loop = asyncio.new_event_loop()
    hub = Hub()
    hub.subscribe("alice", loop)
    loop.close()
    hub.publish("alice", {"n": 1})
    assert hub.count("alice") == 0


# --- the stream
def test_the_stream_needs_a_valid_login_in_its_first_message() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        cases = [
            {"type": "auth", "token": "garbage"},
            {"type": "auth"},
            {"type": "hello", "token": token_of(user)},
            {"token": token_of(user)},
            {"type": "auth", "token": 12345},
        ]
        for first in cases:
            with client.websocket_connect("/api/v1/events") as ws:
                ws.send_json(first)
                with pytest.raises(WebSocketDisconnect) as info:
                    ws.receive_json()
                assert info.value.code == events_router.CLOSE_UNAUTHORIZED


def test_a_token_in_the_url_is_not_a_login() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        with client.websocket_connect(f"/api/v1/events?token={token_of(user)}") as ws:
            ws.send_json({"type": "ping"})
            with pytest.raises(WebSocketDisconnect) as info:
                ws.receive_json()
            assert info.value.code == events_router.CLOSE_UNAUTHORIZED


def test_staying_silent_is_not_a_login(monkeypatch) -> None:
    monkeypatch.setattr(events_router, "AUTH_TIMEOUT_SECONDS", 0.2)
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/events") as ws:
            with pytest.raises(WebSocketDisconnect) as info:
                ws.receive_json()
            assert info.value.code == events_router.CLOSE_UNAUTHORIZED


def test_a_token_for_a_deleted_user_is_refused() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        store.reset()  # the account is gone, the token still verifies
        with client.websocket_connect("/api/v1/events") as ws:
            ws.send_json({"type": "auth", "token": token_of(user)})
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


def test_a_task_is_pushed_through_its_whole_life() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with listen(client, user) as events:
            assert authed(events, user) == {"type": "hello"}

            with _ws(client, agent_id, device) as pc:
                pc.receive_json()
                online = events.receive_json()
                assert online["type"] == "agent" and online["agent"]["id"] == agent_id and online["agent"]["online"] is True

                created = client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad and type hi"}).json()
                accepted, dispatched = events.receive_json(), events.receive_json()
                assert accepted["task"]["id"] == dispatched["task"]["id"] == created["id"]
                assert accepted["task"]["status"] == "pending" and dispatched["task"]["status"] == "running"

                inbound = pc.receive_json()
                pc.send_json({"type": "step", "task_id": inbound["task_id"], "index": 0, "status": "running"})
                assert events.receive_json()["task"]["steps"][0]["status"] == "running"
                pc.send_json({"type": "step", "task_id": inbound["task_id"], "index": 0, "status": "success", "detail": "ok"})
                step = events.receive_json()["task"]["steps"][0]
                assert step["status"] == "success" and step["detail"] == "ok"
                pc.send_json({"type": "step", "task_id": inbound["task_id"], "index": 1, "status": "success"})
                events.receive_json()
                pc.send_json({"type": "result", "task_id": inbound["task_id"], "status": "completed", "summary": "done"})
                final = events.receive_json()["task"]
                assert final["status"] == "completed" and final["summary"] == "done"

            offline = events.receive_json()
            assert offline["type"] == "agent" and offline["agent"]["online"] is False


def test_a_step_screenshot_arrives_as_a_flag_not_as_bytes() -> None:
    import base64

    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as pc, listen(client, user) as events:
            pc.receive_json()
            authed(events, user)
            client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"})
            events.receive_json(), events.receive_json()
            tid = pc.receive_json()["task_id"]
            jpeg = base64.b64encode(b"\xff\xd8\xff" + b"x" * 50).decode()
            pc.send_json({"type": "step", "task_id": tid, "index": 0, "status": "success", "screenshot_b64": jpeg})
            pushed = events.receive_json()
            assert pushed["task"]["steps"][0]["has_screenshot"] is True
            assert "screenshot_b64" not in str(pushed)


def test_cancel_and_removal_are_pushed_immediately() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as pc, listen(client, user) as events:
            pc.receive_json()
            authed(events, user)
            task = client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"}).json()
            events.receive_json(), events.receive_json()
            pc.receive_json()

            client.post(f"/api/v1/tasks/{task['id']}/cancel", headers=user)
            cancelled = events.receive_json()["task"]
            assert cancelled["status"] == "failed" and cancelled["error"] == "Cancelled"

            client.post(f"/api/v1/agents/{agent_id}/revoke", headers=user)
            seen = {events.receive_json()["agent"]["status"]}
            assert "revoked" in seen


def test_one_user_never_sees_anothers_events() -> None:
    with TestClient(app) as client:
        alice = _signup(client, "alice@example.com")
        bob = _signup(client, "bob@example.com")
        agent_id, device = _register(client, alice)
        with listen(client, bob) as bobs, listen(client, alice) as alices:
            authed(bobs, bob)
            authed(alices, alice)
            with _ws(client, agent_id, device) as pc:
                pc.receive_json()
                client.post("/api/v1/tasks", headers=alice, json={"instruction": "open notepad"})
                assert alices.receive_json()["type"] == "agent"
                assert alices.receive_json()["type"] == "task"
            # Anything Alice's activity had sent to Bob would arrive before this marker.
            bob_id = client.get("/api/v1/auth/me", headers=bob).json()["id"]
            hub_module.hub.publish(bob_id, {"type": "marker"})
            assert bobs.receive_json() == {"type": "marker"}


def test_six_phones_is_one_too_many() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        with ExitStack() as stack:
            for _ in range(MAX_SUBSCRIBERS_PER_USER):
                ws = stack.enter_context(listen(client, user))
                assert authed(ws, user) == {"type": "hello"}
            extra = stack.enter_context(listen(client, user))
            extra.send_json({"type": "auth", "token": token_of(user)})
            with pytest.raises(WebSocketDisconnect) as info:
                extra.receive_json()
            assert info.value.code == events_router.CLOSE_TOO_MANY


def test_the_stream_ends_when_the_login_expires(monkeypatch) -> None:
    monkeypatch.setattr(auth, "JWT_EXPIRE_MINUTES", 2 / 60)  # two seconds
    with TestClient(app) as client:
        user = _signup(client)
        with listen(client, user) as events:
            assert authed(events, user) == {"type": "hello"}
            with pytest.raises(WebSocketDisconnect) as info:
                events.receive_json()
            assert info.value.code == events_router.CLOSE_UNAUTHORIZED


def test_leaving_frees_the_slot() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        for _ in range(MAX_SUBSCRIBERS_PER_USER + 2):  # more connections than the cap, one after another
            with listen(client, user) as ws:
                assert authed(ws, user) == {"type": "hello"}


# --- the store must never be broken by its listeners
def test_a_failing_listener_does_not_break_saving(caplog) -> None:
    def broken(kind, user_id, payload):
        raise RuntimeError("listener bug")

    store.subscribe(broken)
    try:
        with TestClient(app) as client:
            user = _signup(client)
            agent_id, device = _register(client, user)
            with _ws(client, agent_id, device) as pc:
                pc.receive_json()
                assert client.post("/api/v1/tasks", headers=user, json={"instruction": "open notepad"}).status_code == 201
    finally:
        store._listeners.remove(broken)
    assert "Store listener failed" in caplog.text


def test_tasks_without_an_owner_publish_nothing() -> None:
    calls: list[tuple] = []
    store.subscribe(lambda *a: calls.append(a))
    try:
        store._emit("task", None, {"id": "x"})
    finally:
        store._listeners.pop()
    assert calls == []
