"""Onboarding of new users: welcome, tour, "first steps" checklist, tips.

What a user has done is read from their data (presentations, exports, Studio
images, top-ups, own templates); what they have seen or closed is stored per
user. The administrator turns the parts on and off (Admin → Onboarding) and
can show everything again to everyone ("seen" marks older than reset_at count
as not seen).
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from models.sql.billing import BillingEntry
from models.sql.image_asset import ImageAsset
from models.sql.key_value import KeyValueSqlModel
from models.sql.presentation import PresentationModel
from models.sql.template_v2 import TemplateV2
from models.sql.user import User
from services.billing import settings as billing_settings
from services.database import async_session_maker
from utils.datetime_utils import get_current_utc_datetime
from utils.get_env import get_app_data_directory_env

LOGGER = logging.getLogger(__name__)

SETTINGS_KEY = "onboarding:settings"
USER_KEY = "onboarding:user:{user_id}"
PARTS = ("welcome", "tour", "checklist", "tips")
TIPS = ("outline-plan", "editor-export", "editor-ai", "studio-brush")
CHECKLIST = ("presentation", "edited", "exported", "studio", "topup", "template")
WELCOME_TEXT_MAX = 400
UNSCOPED = {"skip_owner_scope": True}
STATS_DAYS = 30
STATS_MAX_USERS = 500


def default_settings() -> dict:
    return {**{part: True for part in PARTS}, "welcome_text": "", "reset_at": None}


def normalize_settings(raw: Any) -> dict:
    base = default_settings()
    raw = raw if isinstance(raw, dict) else {}
    result = {part: bool(raw.get(part, base[part])) for part in PARTS}
    result["welcome_text"] = " ".join(str(raw.get("welcome_text") or "").split())[:WELCOME_TEXT_MAX]
    reset_at = raw.get("reset_at")
    result["reset_at"] = reset_at if isinstance(reset_at, str) and _parse(reset_at) else None
    return result


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _now() -> str:
    return get_current_utc_datetime().isoformat()


async def _read(key: str) -> Any:
    try:
        async with async_session_maker() as session:
            row = await session.scalar(select(KeyValueSqlModel).where(KeyValueSqlModel.key == key))
    except SQLAlchemyError:
        LOGGER.warning("Could not read %s", key, exc_info=True)
        return None
    return row.value if row is not None else None


async def _write(key: str, value: dict) -> None:
    async with async_session_maker() as session:
        row = await session.scalar(select(KeyValueSqlModel).where(KeyValueSqlModel.key == key))
        if row is None:
            session.add(KeyValueSqlModel(key=key, value=value))
        else:
            row.value = value
        await session.commit()


async def load_settings() -> dict:
    return normalize_settings(await _read(SETTINGS_KEY))


async def save_settings(raw: dict) -> dict:
    current = await load_settings()
    settings = normalize_settings({**raw, "reset_at": current["reset_at"]})
    await _write(SETTINGS_KEY, settings)
    return settings


async def show_again_to_everyone() -> dict:
    settings = await load_settings()
    settings["reset_at"] = _now()
    await _write(SETTINGS_KEY, settings)
    return settings


async def load_state(user_id: uuid.UUID) -> dict:
    stored = await _read(USER_KEY.format(user_id=user_id))
    state = stored if isinstance(stored, dict) else {}
    tips = state.get("tips") if isinstance(state.get("tips"), dict) else {}
    return {**state, "tips": tips}


async def record(user_id: uuid.UUID, event: str) -> dict:
    """welcome | tour | checklist | edited | tour_restart | preview | tip:<id>."""
    state = await load_state(user_id)
    now = _now()
    if event in ("welcome", "tour", "checklist"):
        state[f"{event}_at"] = now
    elif event == "edited":
        state.setdefault("edited_at", now)
    elif event == "tour_restart":
        state.pop("tour_at", None)
    elif event == "preview":
        state = {"preview": True, "tips": {}, "edited_at": state.get("edited_at")}
    elif event.startswith("tip:") and event[4:] in TIPS:
        state["tips"][event[4:]] = now
    else:
        raise ValueError(event)
    await _write(USER_KEY.format(user_id=user_id), state)
    return state


def _seen(value: Any, reset_at: datetime | None) -> bool:
    moment = _parse(value)
    return moment is not None and (reset_at is None or moment >= reset_at)


def _exported(user_id: uuid.UUID) -> bool:
    folder = os.path.join(get_app_data_directory_env() or "/app_data", "exports", "users", str(user_id))
    try:
        return any(name.lower().endswith((".pptx", ".pdf")) for name in os.listdir(folder))
    except OSError:
        return False


async def checklist(user_id: uuid.UUID, state: dict) -> tuple[dict[str, bool], str | None]:
    """What the user has done, and their latest presentation (for the links)."""
    async with async_session_maker() as session:
        latest = await session.scalar(
            select(PresentationModel.id)
            .where(PresentationModel.owner_id == user_id)
            .order_by(PresentationModel.created_at.desc())
            .limit(1)
            .execution_options(**UNSCOPED)
        )
        assets = (
            await session.scalars(
                select(ImageAsset.extras)
                .where(ImageAsset.owner_id == user_id, ImageAsset.is_uploaded == False)  # noqa: E712
                .limit(500)
                .execution_options(**UNSCOPED)
            )
        ).all()
        topups = await session.scalar(
            select(func.count())
            .select_from(BillingEntry)
            .where(BillingEntry.user_id == user_id, BillingEntry.kind.in_(("topup", "auto_topup")))
        )
        templates = await session.scalar(
            select(func.count())
            .select_from(TemplateV2)
            .where(TemplateV2.owner_id == user_id, TemplateV2.is_default == False)  # noqa: E712
            .execution_options(**UNSCOPED)
        )
    done = {
        "presentation": latest is not None,
        "edited": bool(state.get("edited_at")),
        "exported": _exported(user_id),
        "studio": any(isinstance(extras, dict) and extras.get("source") == "studio" for extras in assets),
        "topup": bool(topups),
        "template": bool(templates),
    }
    if not billing_settings.billing_enabled():
        done.pop("topup")
    return done, str(latest) if latest else None


async def _verified(user_id: uuid.UUID) -> bool:
    """False only for a self-registered user who has not confirmed the e-mail."""
    try:
        async with async_session_maker() as session:
            value = await session.scalar(select(User.is_verified).where(User.id == user_id))
    except SQLAlchemyError:
        return True
    return value is not False


async def overview(user_id: uuid.UUID | None, is_admin: bool) -> dict:
    """What the onboarding shows to this user now."""
    settings = await load_settings()
    hidden = {part: False for part in PARTS}
    if user_id is None:
        return {"show": hidden, "checklist": [], "tips_seen": list(TIPS), "welcome_text": "", "bonus": 0, "verified": True}
    state = await load_state(user_id)
    reset_at = _parse(settings["reset_at"])
    active = (not is_admin) or bool(state.get("preview"))
    done, latest = await checklist(user_id, state)
    items = [{"id": item, "done": done[item]} for item in CHECKLIST if item in done]
    show = {
        "welcome": active and settings["welcome"] and not _seen(state.get("welcome_at"), reset_at),
        "tour": active and settings["tour"] and not _seen(state.get("tour_at"), reset_at),
        "checklist": active
        and settings["checklist"]
        and not _seen(state.get("checklist_at"), reset_at)
        and not all(item["done"] for item in items),
        "tips": active and settings["tips"],
    }
    bonus = billing_settings.signup_bonus() if billing_settings.billing_enabled() else 0
    return {
        "verified": await _verified(user_id),
        "show": show,
        "checklist": items,
        "latest_presentation": latest,
        "tips_seen": [tip for tip in TIPS if _seen(state["tips"].get(tip), reset_at)],
        "welcome_text": settings["welcome_text"],
        "bonus": bonus,
    }


async def stats() -> dict:
    """New users of the last 30 days and how far they got."""
    since = get_current_utc_datetime() - timedelta(days=STATS_DAYS)
    async with async_session_maker() as session:
        users = (
            await session.scalars(
                select(User.id)
                .where(User.is_superuser == False, User.created_at >= since)  # noqa: E712
                .limit(STATS_MAX_USERS)
            )
        ).all()
    result = {"days": STATS_DAYS, "users": len(users), "presentation": 0, "exported": 0, "studio": 0}
    for user_id in users:
        done, _ = await checklist(user_id, await load_state(user_id))
        for item in ("presentation", "exported", "studio"):
            result[item] += int(done[item])
    return result
