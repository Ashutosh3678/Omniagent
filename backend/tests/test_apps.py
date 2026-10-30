"""Opening more than Notepad: apps and folders the PC's owner set up, and Claude Code in a chosen folder."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_api import FakePlanner, _register, _signup, _ws

from app.main import app
from app.planner import _system_prompt
from app.ratelimit import pairing_limiter, planner_limiter
from app.store import store
from app.validation import validate_plan


def setup_function() -> None:
    store.reset()
    pairing_limiter.reset()
    planner_limiter.reset()


def open_app(app_id: str, workspace: str | None = None) -> dict:
    action: dict = {"type": "open_app", "app": app_id}
    if workspace is not None:
        action["workspace"] = workspace
    return {"action": action, "confidence": 1.0}


# --- the validator
def test_paint_opens_when_the_pc_has_it_and_it_is_turned_on() -> None:
    verdict = validate_plan([open_app("paint")], ["paint"], available_apps={"paint"})
    assert [s.description for s in verdict.steps] == ["Open Paint"]


def test_an_app_the_pc_does_not_have_says_so() -> None:
    verdict = validate_plan([open_app("paint")], ["paint"], available_apps={"notepad"})
    assert verdict.held_back[0].reason == "unknown_app"
    assert "not set up on this PC" in verdict.held_back[0].detail


def test_an_app_that_is_switched_off_says_where_to_switch_it_on() -> None:
    verdict = validate_plan([open_app("paint")], ["notepad"], available_apps={"paint", "notepad"})
    assert verdict.held_back[0].reason == "app_not_permitted"
    assert "Turn it on in Devices" in verdict.held_back[0].detail


def test_programs_the_owner_added_can_be_opened_by_their_reported_id() -> None:
    verdict = validate_plan([open_app("spotify")], ["spotify"], available_apps={"spotify"})
    assert [s.description for s in verdict.steps] == ["Open Spotify"]


@pytest.mark.parametrize("app_id", ["Paint", "calc.exe", "..\\evil", "a b", "x" * 33, ""])
def test_app_ids_are_plain_lowercase_words(app_id: str) -> None:
    verdict = validate_plan([open_app(app_id)], ["notepad"], available_apps={"notepad"})
    assert verdict.steps == [] and verdict.held_back[0].reason in {"invalid_parameters", "unknown_app"}


def test_claude_code_needs_a_folder_from_the_pcs_own_list() -> None:
    common = {"permitted_apps": ["claude_code"], "available_apps": {"claude_code"}}
    ok = validate_plan([open_app("claude_code", "omniagent")], workspaces={"omniagent", "site"}, **common)
    assert [s.description for s in ok.steps] == ["Open Claude Code in omniagent"]
    assert ok.steps[0].action == {"type": "open_app", "app": "claude_code", "workspace": "omniagent"}

    missing = validate_plan([open_app("claude_code")], workspaces={"omniagent"}, **common)
    assert missing.held_back[0].reason == "invalid_parameters" and "folder" in missing.held_back[0].detail

    unknown = validate_plan([open_app("claude_code", "secrets")], workspaces={"omniagent"}, **common)
    assert unknown.held_back[0].reason == "unknown_workspace"

    not_reported = validate_plan([open_app("claude_code", "omniagent")], **common)
    assert not_reported.held_back[0].reason == "unknown_workspace"


@pytest.mark.parametrize("workspace", ["C:\\Windows", "..\\..\\x", "a/b", "C:", "x" * 81, "$(whoami)", "a;b"])
def test_a_folder_is_a_name_never_a_path(workspace: str) -> None:
    verdict = validate_plan(
        [open_app("claude_code", workspace)], ["claude_code"], available_apps={"claude_code"}, workspaces={workspace}
    )
    assert verdict.steps == [] and verdict.held_back[0].reason == "invalid_parameters"


def test_other_apps_do_not_take_a_folder() -> None:
    verdict = validate_plan([open_app("paint", "omniagent")], ["paint"], available_apps={"paint"}, workspaces={"omniagent"})
    assert verdict.held_back[0].reason == "invalid_parameters"


def test_the_prompt_for_claude_code_is_a_plan_for_the_app_that_must_be_confirmed_like_any_other() -> None:
    plan = [
        open_app("claude_code", "omniagent"),
        {"action": {"type": "wait", "seconds": 6}},
        {"action": {"type": "type_text", "text": "Fix the failing test in backend/tests"}},
        {"action": {"type": "press_key", "key": "enter"}},
    ]
    verdict = validate_plan(
        plan, ["claude_code"], available_apps={"claude_code"}, workspaces={"omniagent"}
    )
    assert len(verdict.steps) == 4 and verdict.held_back == []


# --- the planner prompt
def test_the_prompt_lists_the_apps_and_folders_and_how_to_use_claude_code() -> None:
    apps = [
        {"id": "paint", "label": "Paint", "needs_workspace": False},
        {"id": "claude_code", "label": "Claude Code", "needs_workspace": True},
    ]
    prompt = _system_prompt(["paint", "claude_code"], ["open_app", "type_text", "wait", "press_key"], apps, ["omniagent", "site"])
    assert "paint - Paint" in prompt and "claude_code - Claude Code (needs a folder)" in prompt
    assert "Folders set up on this PC: omniagent, site." in prompt
    assert '"workspace"' in prompt and "To give Claude Code a prompt" in prompt
    assert "Never invent a folder" in prompt


def test_the_prompt_stays_simple_without_claude_code() -> None:
    apps = [{"id": "paint", "label": "Paint", "needs_workspace": False}]
    prompt = _system_prompt(["paint"], ["open_app"], apps, [])
    assert "Folders set up" not in prompt and "Claude Code" not in prompt and '"workspace"' not in prompt


def test_the_prompt_for_a_pc_that_has_not_reported_apps_is_the_old_one() -> None:
    assert "Apps this PC may use: notepad." in _system_prompt(["notepad"], ["open_app"])


# --- through the API
def report(ws, apps: list[dict], workspaces: list[str] | None = None, actions: list[str] | None = None) -> None:
    message: dict = {
        "type": "capabilities",
        "actions": actions or ["open_app", "type_text", "press_key", "wait", "screenshot"],
        "apps": apps,
    }
    if workspaces is not None:
        message["workspaces"] = workspaces
    ws.send_json(message)


PAINT = {"id": "paint", "label": "Paint"}
NOTEPAD = {"id": "notepad", "label": "Notepad"}
CLAUDE = {"id": "claude_code", "label": "Claude Code", "needs_workspace": True}


def test_a_reported_app_list_is_stored_and_shown_to_the_phone() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            report(ws, [NOTEPAD, PAINT, CLAUDE], ["omniagent"])
            body = client.get("/api/v1/agents", headers=user).json()[0]
            assert [a["id"] for a in body["apps"]] == ["notepad", "paint", "claude_code"]
            assert body["apps"][2]["needs_workspace"] is True
            assert body["workspaces"] == ["omniagent"]


def test_an_older_pc_is_treated_as_having_only_notepad_and_the_browser() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        _register(client, user)
        body = client.get("/api/v1/agents", headers=user).json()[0]
        assert sorted(a["id"] for a in body["apps"]) == ["browser", "notepad"]
        assert body["workspaces"] == []


def test_the_first_report_switches_on_only_the_harmless_defaults_once() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        client.patch(f"/api/v1/agents/{agent_id}", headers=user, json={"permitted_apps": ["notepad"]})  # an older PC
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            report(ws, [NOTEPAD, PAINT, CLAUDE], ["omniagent"])
            permitted = client.get("/api/v1/agents", headers=user).json()[0]["permitted_apps"]
            assert permitted == ["notepad", "paint"]  # Paint on; Claude Code stays off until the user says so

            client.patch(f"/api/v1/agents/{agent_id}", headers=user, json={"permitted_apps": ["notepad"]})
            report(ws, [NOTEPAD, PAINT, CLAUDE], ["omniagent"])
            assert client.get("/api/v1/agents", headers=user).json()[0]["permitted_apps"] == ["notepad"]
        events = [e["event"] for e in client.get("/api/v1/audit", headers=user).json()]
        assert events.count("default_apps_granted") == 1


def test_malformed_app_reports_are_cleaned_not_trusted() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            report(
                ws,
                [PAINT, {"id": "Bad Id!"}, {"id": "paint", "label": "Duplicate"}, "nope", {"label": "no id"}, {"id": "x" * 40}],
                ["omniagent", "C:\\Windows", "a/b", 5, "omniagent"],
            )
            body = client.get("/api/v1/agents", headers=user).json()[0]
            assert [a["id"] for a in body["apps"]] == ["paint"] and body["apps"][0]["label"] == "Paint"
            assert body["workspaces"] == ["omniagent"]


def test_the_phone_can_switch_on_any_app_the_pc_reported_and_nothing_else() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        url = f"/api/v1/agents/{agent_id}"
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            report(ws, [NOTEPAD, {"id": "spotify", "label": "Spotify"}])
            assert client.patch(url, headers=user, json={"permitted_apps": ["notepad", "spotify"]}).status_code == 200
            assert client.patch(url, headers=user, json={"permitted_apps": ["notepad", "regedit"]}).status_code == 422


def test_paint_runs_when_it_is_set_up_and_on() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            report(ws, [NOTEPAD, PAINT])
            created = client.post("/api/v1/tasks", headers=user, json={"instruction": "open paint"})
            assert created.status_code == 201, created.text
            assert ws.receive_json()["plan"] == [{"index": 0, "action": {"type": "open_app", "app": "paint"}}]


def test_paint_is_refused_with_a_useful_reason_when_the_pc_does_not_have_it() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            report(ws, [NOTEPAD])
            response = client.post("/api/v1/tasks", headers=user, json={"instruction": "open paint"})
            assert response.status_code == 403 and "not set up on this PC" in response.json()["detail"]


def test_an_app_switched_off_is_refused_and_says_how_to_switch_it_on() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        client.patch(f"/api/v1/agents/{agent_id}", headers=user, json={"permitted_apps": ["notepad"]})
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            ws.send_json({"type": "capabilities", "actions": ["open_app"], "apps": [NOTEPAD, PAINT]})
            # reports from an already-reported PC never switch anything on
            client.patch(f"/api/v1/agents/{agent_id}", headers=user, json={"permitted_apps": ["notepad"]})
            response = client.post("/api/v1/tasks", headers=user, json={"instruction": "open paint"})
            assert response.status_code == 403 and "Turn it on in Devices" in response.json()["detail"]


def test_claude_code_in_a_chosen_folder_goes_through_the_normal_checks(monkeypatch) -> None:
    prompt = "Fix the failing test in backend/tests"
    plan = [
        open_app("claude_code", "omniagent"),
        {"action": {"type": "wait", "seconds": 6}, "confidence": 0.9},
        {"action": {"type": "type_text", "text": prompt}, "confidence": 0.9},
        {"action": {"type": "press_key", "key": "enter"}, "confidence": 0.9},
    ]
    fake = FakePlanner(plan)
    monkeypatch.setattr("app.planner.get_planner", lambda: fake)
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        url = f"/api/v1/agents/{agent_id}"
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            report(ws, [NOTEPAD, CLAUDE], ["omniagent", "site"])

            # Off by default: a fresh PC does not let Claude Code in until the user turns it on.
            off = client.post("/api/v1/plans/preview", headers=user, json={"instruction": "ask claude code to fix the test"}).json()
            assert off["runnable"] is False and off["held_back"][0]["reason"] == "app_not_permitted"

            client.patch(url, headers=user, json={"permitted_apps": ["notepad", "claude_code"]})
            preview = client.post("/api/v1/plans/preview", headers=user, json={"instruction": "ask claude code to fix the test"}).json()
            assert preview["runnable"] is True and preview["held_back"] == []
            assert preview["steps"][0]["description"] == "Open Claude Code in omniagent"
            # the planner was told the folders and which apps need one
            assert fake.workspaces == ["omniagent", "site"]
            assert {"id": "claude_code", "label": "Claude Code", "needs_workspace": True} in fake.apps

            created = client.post("/api/v1/tasks", headers=user, json={"instruction": "x", "plan": preview["plan"]})
            assert created.status_code == 201, created.text
            sent = ws.receive_json()["plan"]
            assert [s["action"]["type"] for s in sent] == ["open_app", "wait", "type_text", "press_key"]
            assert sent[0]["action"] == {"type": "open_app", "app": "claude_code", "workspace": "omniagent"}
            assert sent[2]["action"]["text"] == prompt


def test_a_folder_the_pc_does_not_have_is_refused_before_anything_runs() -> None:
    with TestClient(app) as client:
        user = _signup(client)
        agent_id, device = _register(client, user)
        client.patch(f"/api/v1/agents/{agent_id}", headers=user, json={"permitted_apps": ["notepad", "claude_code"]})
        with _ws(client, agent_id, device) as ws:
            ws.receive_json()
            report(ws, [CLAUDE], ["omniagent"])
            for bad in ("secrets", "C:\\Users\\me\\Documents", "../etc"):
                response = client.post(
                    "/api/v1/tasks", headers=user, json={"instruction": "x", "plan": [open_app("claude_code", bad)]}
                )
                assert response.status_code == 422, bad
            assert client.get("/api/v1/tasks", headers=user).json() == []
            reasons = {e["reason"] for e in client.get("/api/v1/audit", headers=user).json() if e["event"] == "dispatch_denied"}
            assert "unknown_workspace" in reasons or "invalid_parameters" in reasons


def test_simple_app_phrases_need_no_ai() -> None:
    from app.actions import plan_from_instruction

    assert plan_from_instruction("Open Paint") == [{"action": {"type": "open_app", "app": "paint"}, "confidence": 1.0}]
    assert plan_from_instruction("open calc")[0]["action"]["app"] == "calculator"
    assert plan_from_instruction("open MS Paint")[0]["action"]["app"] == "paint"
    with pytest.raises(Exception):
        plan_from_instruction("open paint and format c:")
