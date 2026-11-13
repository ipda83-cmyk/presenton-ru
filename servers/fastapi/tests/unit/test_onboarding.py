import asyncio
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.auth import context
from api.v1.onboarding import router as onboarding_router
from services import onboarding
from utils.i18n.middleware import LocaleMiddleware

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture()
def store(monkeypatch, tmp_path):
    """Settings and user marks in memory; the checklist from a dict."""
    box: dict = {}
    done = {item: False for item in onboarding.CHECKLIST}

    async def read(key):
        return box.get(key)

    async def write(key, value):
        box[key] = value

    async def checklist(user_id, state):
        return {**done, "edited": bool(state.get("edited_at"))}, None

    monkeypatch.setattr(onboarding, "_read", read)
    monkeypatch.setattr(onboarding, "_write", write)
    async def stats():
        return {"days": 30, "users": 0, "presentation": 0, "exported": 0, "studio": 0}

    monkeypatch.setattr(onboarding, "checklist", checklist)
    monkeypatch.setattr(onboarding, "stats", stats)
    monkeypatch.setenv("APP_DATA_DIRECTORY", str(tmp_path))
    return box, done


def _as(user_id, is_admin=False):
    owner = context.set_current_owner_id(user_id)
    admin = context.set_current_owner_is_admin(is_admin)
    return owner, admin


def _client():
    app = FastAPI()
    app.add_middleware(LocaleMiddleware)
    app.include_router(onboarding_router.API_V1_ONBOARDING_ROUTER)
    app.include_router(onboarding_router.API_V1_ADMIN_ONBOARDING_ROUTER)
    return TestClient(app)


def test_a_new_user_sees_every_part(store):
    view = asyncio.run(onboarding.overview(USER, False))
    assert view["show"] == {"welcome": True, "tour": True, "checklist": True, "tips": True}
    assert view["tips_seen"] == []
    assert [item["id"] for item in view["checklist"]] == list(onboarding.CHECKLIST)


def test_marks_hide_what_was_seen(store):
    for event in ("welcome", "tour", "tip:editor-export", "edited"):
        asyncio.run(onboarding.record(USER, event))
    view = asyncio.run(onboarding.overview(USER, False))
    assert view["show"]["welcome"] is False and view["show"]["tour"] is False
    assert view["tips_seen"] == ["editor-export"]
    assert {item["id"]: item["done"] for item in view["checklist"]}["edited"] is True

    asyncio.run(onboarding.record(USER, "checklist"))
    assert asyncio.run(onboarding.overview(USER, False))["show"]["checklist"] is False


def test_the_checklist_disappears_when_everything_is_done(store):
    _, done = store
    done.update({item: True for item in onboarding.CHECKLIST})
    asyncio.run(onboarding.record(USER, "edited"))
    assert asyncio.run(onboarding.overview(USER, False))["show"]["checklist"] is False


def test_unknown_events_are_refused(store):
    for event in ("tip:nowhere", "everything", "welcome_at"):
        with pytest.raises(ValueError):
            asyncio.run(onboarding.record(USER, event))


def test_administrators_see_it_only_when_they_ask(store):
    assert not any(asyncio.run(onboarding.overview(USER, True))["show"].values())
    asyncio.run(onboarding.record(USER, "preview"))
    assert asyncio.run(onboarding.overview(USER, True))["show"]["welcome"] is True


def test_turned_off_parts_are_not_shown(store):
    asyncio.run(onboarding.save_settings({"welcome": False, "tour": True, "checklist": False, "tips": False}))
    show = asyncio.run(onboarding.overview(USER, False))["show"]
    assert show == {"welcome": False, "tour": True, "checklist": False, "tips": False}


def test_show_again_brings_back_what_was_seen_before(store):
    asyncio.run(onboarding.record(USER, "welcome"))
    asyncio.run(onboarding.record(USER, "tip:studio-brush"))
    box, _ = store
    key = onboarding.USER_KEY.format(user_id=USER)
    box[key]["welcome_at"] = "2026-01-01T00:00:00+00:00"
    box[key]["tips"]["studio-brush"] = "2026-01-01T00:00:00+00:00"

    asyncio.run(onboarding.show_again_to_everyone())
    view = asyncio.run(onboarding.overview(USER, False))
    assert view["show"]["welcome"] is True and view["tips_seen"] == []
    # Saving the settings keeps the reset.
    asyncio.run(onboarding.save_settings({"welcome": True}))
    assert asyncio.run(onboarding.load_settings())["reset_at"]


def test_restart_the_tour(store):
    asyncio.run(onboarding.record(USER, "tour"))
    asyncio.run(onboarding.record(USER, "tour_restart"))
    assert asyncio.run(onboarding.overview(USER, False))["show"]["tour"] is True


def test_settings_are_cleaned_up():
    settings = onboarding.normalize_settings({"welcome": 0, "welcome_text": "  Привет  " + "а" * 600, "reset_at": "вчера"})
    assert settings["welcome"] is False and settings["tour"] is True
    assert settings["welcome_text"].startswith("Привет а") and len(settings["welcome_text"]) == onboarding.WELCOME_TEXT_MAX
    assert settings["reset_at"] is None


def test_an_export_counts_once_a_file_is_there(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIRECTORY", str(tmp_path))
    assert onboarding._exported(USER) is False
    folder = tmp_path / "exports" / "users" / str(USER)
    folder.mkdir(parents=True)
    (folder / "deck.pptx").write_bytes(b"x")
    assert onboarding._exported(USER) is True


def test_the_api_marks_and_answers_for_the_signed_in_user(store):
    tokens = _as(USER)
    try:
        client = _client()
        assert client.get("/api/v1/onboarding").json()["show"]["welcome"] is True
        answer = client.post("/api/v1/onboarding/events", json={"event": "welcome"}).json()
        assert answer["show"]["welcome"] is False
        assert client.post("/api/v1/onboarding/events", json={"event": "hack"}).status_code == 400
        state = client.put("/api/v1/admin/onboarding", json={"welcome": True, "tour": False, "checklist": True, "tips": True, "welcome_text": "Здравствуйте"}).json()
        assert state["settings"]["tour"] is False and state["settings"]["welcome_text"] == "Здравствуйте"
    finally:
        context.reset_current_owner_is_admin(tokens[1])
        context.reset_current_owner_id(tokens[0])


def test_without_a_user_nothing_is_shown(store):
    view = asyncio.run(onboarding.overview(None, False))
    assert not any(view["show"].values())
