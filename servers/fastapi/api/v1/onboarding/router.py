"""Onboarding: the signed-in user's state and marks; Admin → Onboarding.

The /api/v1/admin/ prefix is guarded by the session middleware.
"""

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.v1.auth.context import get_current_owner_id, get_current_owner_is_admin
from services import onboarding
from utils.i18n import http_error

API_V1_ONBOARDING_ROUTER = APIRouter(prefix="/api/v1/onboarding", tags=["Onboarding"])
API_V1_ADMIN_ONBOARDING_ROUTER = APIRouter(prefix="/api/v1/admin/onboarding", tags=["Onboarding"])


class OnboardingEvent(BaseModel):
    event: str = Field(max_length=64)


class OnboardingSettings(BaseModel):
    welcome: bool = True
    tour: bool = True
    checklist: bool = True
    tips: bool = True
    welcome_text: Optional[str] = Field(default="", max_length=onboarding.WELCOME_TEXT_MAX)


async def _current() -> dict:
    return await onboarding.overview(get_current_owner_id(), get_current_owner_is_admin())


@API_V1_ONBOARDING_ROUTER.get("")
async def read_onboarding():
    return await _current()


@API_V1_ONBOARDING_ROUTER.post("/events")
async def onboarding_event(body: OnboardingEvent):
    user_id = get_current_owner_id()
    if user_id is None:
        return await _current()
    try:
        await onboarding.record(user_id, body.event)
    except ValueError:
        raise http_error(400, "err.onboarding.unknownEvent", event=body.event[:64])
    return await _current()


async def _admin_state() -> dict:
    return {"settings": await onboarding.load_settings(), "stats": await onboarding.stats()}


@API_V1_ADMIN_ONBOARDING_ROUTER.get("")
async def admin_onboarding():
    return await _admin_state()


@API_V1_ADMIN_ONBOARDING_ROUTER.put("")
async def admin_onboarding_save(body: OnboardingSettings):
    await onboarding.save_settings(body.model_dump())
    return await _admin_state()


@API_V1_ADMIN_ONBOARDING_ROUTER.post("/show-again")
async def admin_onboarding_show_again():
    """Everyone sees the welcome, the tour and the tips once more."""
    await onboarding.show_again_to_everyone()
    return await _admin_state()
