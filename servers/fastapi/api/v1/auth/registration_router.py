"""Self sign-up, e-mail confirmation and password reset; Admin → Sign-up.

Public (see _PUBLIC_AUTH_PATHS in api/middlewares.py): registration info,
register, verify-email, password/forgot, password/reset. Resending the
confirmation needs a session; the /api/v1/admin/ prefix is for administrators.
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from api.v1.auth.config import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS
from api.v1.auth.locale import get_user_locale, set_locale_cookie, set_user_locale
from api.v1.auth.users import PASSWORD_HELPER, get_jwt_strategy, read_user_from_cookie, serialize_user
from models.sql.user import User
from services import legal
from services.accounts import mailer, registration, tokens
from services.billing import ledger
from services.billing import settings as billing_settings
from services.database import get_async_session
from utils.i18n import get_current_locale, http_error

LOGGER = logging.getLogger(__name__)

PASSWORD_MIN = 8

API_V1_REGISTRATION_ROUTER = APIRouter(prefix="/api/v1/auth", tags=["Auth"])
API_V1_ADMIN_REGISTRATION_ROUTER = APIRouter(prefix="/api/v1/admin/registration", tags=["Auth"])


class RegisterRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=PASSWORD_MIN, max_length=128)
    accept_offer: bool = False
    accept_privacy: bool = False
    captcha: Optional[str] = Field(default=None, max_length=4096)


class TokenRequest(BaseModel):
    token: str = Field(max_length=4096)


class ForgotRequest(BaseModel):
    email: str = Field(max_length=254)


class ResetRequest(BaseModel):
    token: str = Field(max_length=4096)
    password: str = Field(min_length=PASSWORD_MIN, max_length=128)


class RegistrationSettings(BaseModel):
    open: bool = False
    ip_daily_limit: int = Field(default=registration.DEFAULT_IP_DAILY_LIMIT, ge=1, le=1000)
    blocked_domains: list[str] = Field(default_factory=list, max_length=registration.MAX_EXTRA_DOMAINS)


class TestEmailRequest(BaseModel):
    to: Optional[str] = Field(default=None, max_length=254)


def _secure(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",", 1)[0].strip()
    return proto == "https"


async def _signed_in(response: JSONResponse, user: User, request: Request) -> JSONResponse:
    token = await get_jwt_strategy().write_token(user)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=_secure(request),
        samesite="lax",
        path="/",
    )
    return response


async def _send(user: User, kind: str, locale: str) -> bool:
    """A letter with a fresh link; False when it could not be sent."""
    path = "/verify-email" if kind == "verify" else "/reset-password"
    try:
        url = mailer.link(f"{path}?token={tokens.make(user, kind)}")
        subject, text, body = mailer.letter(kind, locale, url)
        await mailer.send(user.username, subject, text, body)
    except mailer.MailError:
        return False
    return True


async def _user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(func.lower(User.username) == email.casefold()))


async def _locale_of(session: AsyncSession, user: User) -> str:
    stored = await get_user_locale(session, user.id)
    return stored if stored in ("ru", "en") else get_current_locale()


# ---------------------------------------------------------------- public
@API_V1_REGISTRATION_ROUTER.get("/registration")
async def registration_info():
    settings = await registration.load_settings()
    return {
        "open": settings["open"] and mailer.configured(),
        "password_min": PASSWORD_MIN,
        "captcha_key": registration.captcha_client_key() if registration.captcha_enabled() else None,
        "offer_url": billing_settings.offer_url() or await legal.public_path("offer"),
        "privacy_url": await legal.public_path("privacy"),
        "bonus": billing_settings.signup_bonus() if billing_settings.billing_enabled() else 0,
    }


@API_V1_REGISTRATION_ROUTER.post("/register")
async def register(body: RegisterRequest, request: Request, session: AsyncSession = Depends(get_async_session)):
    settings = await registration.load_settings()
    if not settings["open"] or not mailer.configured():
        raise http_error(403, "auth.registrationClosed")
    if not (body.accept_offer and body.accept_privacy):
        raise http_error(422, "auth.consentRequired")
    try:
        email = registration.normalize_email(body.email)
    except registration.InvalidEmail:
        raise http_error(422, "auth.emailInvalid")
    if registration.is_disposable(email, settings):
        raise http_error(422, "auth.emailDisposable")
    ip = registration.client_ip(request)
    if not await registration.captcha_passed(body.captcha, ip):
        raise http_error(400, "auth.captchaFailed")
    if await _user_by_email(session, email) is not None:
        raise http_error(409, "auth.emailTaken")
    if not await registration.allow("signup-ip", ip, window=86400, limit=settings["ip_daily_limit"]):
        raise http_error(429, "auth.tooManyRegistrations")

    user = User(
        username=email,
        hashed_password=PASSWORD_HELPER.hash(body.password),
        is_active=True,
        is_verified=False,
        is_superuser=False,
        auth_version=1,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise http_error(409, "auth.emailTaken")
    await session.refresh(user)
    user_id = user.id
    locale = get_current_locale()
    await set_user_locale(session, user_id, locale)
    await registration.record_consent(user_id, await legal.versions(), ip)
    sent = await _send(user, "verify", locale)
    LOGGER.info("Signed up %s (letter %s)", user_id, "sent" if sent else "not sent")

    response = JSONResponse({"configured": True, "authenticated": True, "letter_sent": sent, **serialize_user(user)})
    set_locale_cookie(response, locale, secure=_secure(request))
    return await _signed_in(response, user, request)


@API_V1_REGISTRATION_ROUTER.post("/verify-email")
async def verify_email(body: TokenRequest, session: AsyncSession = Depends(get_async_session)):
    payload = tokens.read(body.token, "verify")
    user = await session.get(User, uuid.UUID(payload["sub"])) if payload else None
    if payload is None or not tokens.matches(user, payload):
        raise http_error(400, "auth.linkInvalid")
    user_id = user.id
    if not user.is_verified:
        user.is_verified = True
        await session.commit()
    granted = await ledger.grant_signup_bonus(user_id) if billing_settings.billing_enabled() else 0
    return {"verified": True, "bonus": granted}


@API_V1_REGISTRATION_ROUTER.post("/password/forgot")
async def forgot_password(body: ForgotRequest, request: Request, session: AsyncSession = Depends(get_async_session)):
    """Always the same answer, so it does not tell which addresses exist."""
    try:
        email = registration.normalize_email(body.email)
    except registration.InvalidEmail:
        raise http_error(422, "auth.emailInvalid")
    if not mailer.configured():
        raise http_error(503, "auth.mailUnavailable")
    ip = registration.client_ip(request)
    if not await registration.allow_letter(email, ip, "reset"):
        raise http_error(429, "auth.tooManyLetters")
    user = await _user_by_email(session, email)
    if user is not None and user.is_active:
        await _send(user, "reset", await _locale_of(session, user))
    return {"sent": True}


@API_V1_REGISTRATION_ROUTER.post("/password/reset")
async def reset_password(body: ResetRequest, request: Request, session: AsyncSession = Depends(get_async_session)):
    payload = tokens.read(body.token, "reset")
    user = await session.get(User, uuid.UUID(payload["sub"])) if payload else None
    if payload is None or not tokens.matches(user, payload):
        raise http_error(400, "auth.linkInvalid")
    user.hashed_password = PASSWORD_HELPER.hash(body.password)
    user.auth_version += 1  # every other session signs out
    was_verified = user.is_verified
    user.is_verified = True  # the link came by e-mail
    await session.commit()
    await session.refresh(user)
    if not was_verified and billing_settings.billing_enabled():
        await ledger.grant_signup_bonus(user.id)
    response = JSONResponse({"configured": True, "authenticated": True, **serialize_user(user)})
    return await _signed_in(response, user, request)


# ---------------------------------------------------------------- signed in
@API_V1_REGISTRATION_ROUTER.post("/verify-email/resend")
async def resend_confirmation(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user: User | None = Depends(read_user_from_cookie),
):
    if user is None:
        raise http_error(401, "auth.unauthorized")
    if user.is_verified:
        return {"sent": False, "verified": True}
    if not mailer.configured():
        raise http_error(503, "auth.mailUnavailable")
    if not await registration.allow_letter(user.username, registration.client_ip(request), "verify"):
        raise http_error(429, "auth.tooManyLetters")
    if not await _send(user, "verify", await _locale_of(session, user)):
        raise http_error(502, "auth.mailFailed")
    return {"sent": True, "verified": False}


# ---------------------------------------------------------------- admin
async def _admin_state() -> dict:
    return {
        "settings": await registration.load_settings(),
        "mail": {"configured": mailer.configured(), "missing": mailer.missing_settings()},
        "captcha": {"configured": registration.captcha_enabled()},
        "builtin_blocked_domains": len(registration.builtin_domains()),
    }


@API_V1_ADMIN_REGISTRATION_ROUTER.get("")
async def admin_registration():
    return await _admin_state()


@API_V1_ADMIN_REGISTRATION_ROUTER.put("")
async def admin_registration_save(body: RegistrationSettings):
    if body.open and not mailer.configured():
        raise http_error(400, "auth.mailRequired", missing=", ".join(mailer.missing_settings()))
    await registration.save_settings(body.model_dump())
    return await _admin_state()


@API_V1_ADMIN_REGISTRATION_ROUTER.post("/test-email")
async def admin_test_email(
    body: TestEmailRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User | None = Depends(read_user_from_cookie),
):
    if not mailer.configured():
        raise http_error(400, "auth.mailRequired", missing=", ".join(mailer.missing_settings()))
    target = body.to or (user.username if user else "")
    try:
        target = registration.normalize_email(target)
    except registration.InvalidEmail:
        raise http_error(422, "auth.emailInvalid")
    locale = await _locale_of(session, user) if user else get_current_locale()
    subject, text, html_body = mailer.letter("test", locale, mailer.link("/"))
    try:
        await mailer.send(target, subject, text, html_body)
    except mailer.MailError as error:
        raise http_error(502, "auth.mailTestFailed", error=str(error)[:300])
    return {"sent": True, "to": target}
