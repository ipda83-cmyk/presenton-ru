"""Self sign-up rules: open or closed, address checks, limits, captcha, consent.

Settings live in the key-value table (Admin → Sign-up); sign-up is closed
until an administrator opens it, and it can only be opened with working mail.
"""

import ipaddress
import logging
import os
import time
import uuid
from typing import Any

import aiohttp
from email_validator import EmailNotValidError, validate_email
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from models.sql.key_value import KeyValueSqlModel
from services.database import async_session_maker
from utils.datetime_utils import get_current_utc_datetime

LOGGER = logging.getLogger(__name__)

SETTINGS_KEY = "auth:registration"
RATE_KEY = "rate:{bucket}:{subject}"
CONSENT_KEY = "consent:{user_id}"
DOMAINS_PATH = os.path.join(os.path.dirname(__file__), "disposable_domains.txt")
DEFAULT_IP_DAILY_LIMIT = 3
MAX_EXTRA_DOMAINS = 500
CAPTCHA_VALIDATE_URL = "https://smartcaptcha.yandexcloud.net/validate"
CAPTCHA_TIMEOUT = aiohttp.ClientTimeout(total=8)

# (bucket, window seconds, limit) for letters; sign-ups per IP come from settings.
LETTER_LIMITS = {
    "letter-email": (3600, 3),
    "letter-ip": (3600, 10),
}


class InvalidEmail(ValueError):
    pass


# ---------------------------------------------------------------- storage
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


# ---------------------------------------------------------------- settings
def default_settings() -> dict:
    return {"open": False, "ip_daily_limit": DEFAULT_IP_DAILY_LIMIT, "blocked_domains": []}


def _domain(value: Any) -> str:
    return str(value or "").strip().lower().lstrip("@").rstrip(".")


def normalize_settings(raw: Any) -> dict:
    base = default_settings()
    raw = raw if isinstance(raw, dict) else {}
    try:
        limit = int(raw.get("ip_daily_limit", base["ip_daily_limit"]))
    except (TypeError, ValueError):
        limit = base["ip_daily_limit"]
    domains = raw.get("blocked_domains") if isinstance(raw.get("blocked_domains"), list) else []
    cleaned = sorted({_domain(item) for item in domains if "." in _domain(item) and len(_domain(item)) <= 253})
    return {
        "open": bool(raw.get("open", base["open"])),
        "ip_daily_limit": min(max(limit, 1), 1000),
        "blocked_domains": cleaned[:MAX_EXTRA_DOMAINS],
    }


async def load_settings() -> dict:
    return normalize_settings(await _read(SETTINGS_KEY))


async def save_settings(raw: dict) -> dict:
    settings = normalize_settings(raw)
    await _write(SETTINGS_KEY, settings)
    return settings


# ---------------------------------------------------------------- addresses
_BUILTIN_DOMAINS: frozenset[str] | None = None


def builtin_domains() -> frozenset[str]:
    global _BUILTIN_DOMAINS
    if _BUILTIN_DOMAINS is None:
        with open(DOMAINS_PATH, encoding="utf-8") as handle:
            _BUILTIN_DOMAINS = frozenset(
                _domain(line) for line in handle if line.strip() and not line.lstrip().startswith("#")
            )
    return _BUILTIN_DOMAINS


def normalize_email(value: str) -> str:
    """The address in lower case, or InvalidEmail. No DNS lookups."""
    try:
        result = validate_email(str(value or "").strip(), check_deliverability=False)
    except EmailNotValidError as error:
        raise InvalidEmail(str(error)) from error
    return result.normalized.casefold()


def is_disposable(email: str, settings: dict) -> bool:
    domain = email.rsplit("@", 1)[-1]
    blocked = builtin_domains() | frozenset(settings.get("blocked_domains") or ())
    parts = domain.split(".")
    return any(".".join(parts[index:]) in blocked for index in range(len(parts) - 1))


# ---------------------------------------------------------------- client address
def client_ip(request: Request) -> str:
    """The visitor's address behind the platform proxy and nginx.

    X-Forwarded-For is read from the right, skipping private and loopback hops
    (nginx, the RelaxNet ingress): the first public one is the hop the platform
    itself saw, which a visitor cannot forge by sending their own header.
    """
    forwarded = request.headers.get("x-forwarded-for") or ""
    for part in reversed([item.strip() for item in forwarded.split(",") if item.strip()]):
        try:
            address = ipaddress.ip_address(part)
        except ValueError:
            continue
        if address.is_global:
            return str(address)
    return request.client.host if request.client else "unknown"


# ---------------------------------------------------------------- limits
async def allow(bucket: str, subject: str, *, window: int, limit: int) -> bool:
    """Count one more event of `subject` in `bucket`; False when over the limit.

    Approximate under concurrency (two simultaneous requests may both pass),
    which is fine for abuse limits.
    """
    key = RATE_KEY.format(bucket=bucket, subject=subject.casefold()[:200])
    now = time.time()
    stored = await _read(key)
    times = [moment for moment in (stored or {}).get("times", []) if isinstance(moment, (int, float)) and now - moment < window]
    if len(times) >= limit:
        return False
    times.append(now)
    await _write(key, {"times": times[-limit:]})
    return True


async def allow_letter(email: str, ip: str, kind: str) -> bool:
    """Confirmation and reset letters are counted apart: asking for the
    confirmation again must not lock someone out of resetting the password."""
    window, limit = LETTER_LIMITS["letter-ip"]
    if not await allow(f"letter-ip-{kind}", ip, window=window, limit=limit):
        return False
    window, limit = LETTER_LIMITS["letter-email"]
    return await allow(f"letter-email-{kind}", email, window=window, limit=limit)


# ---------------------------------------------------------------- captcha
def captcha_client_key() -> str:
    return (os.getenv("SMARTCAPTCHA_CLIENT_KEY") or "").strip()


def captcha_server_key() -> str:
    return (os.getenv("SMARTCAPTCHA_SERVER_KEY") or "").strip()


def captcha_enabled() -> bool:
    return bool(captcha_client_key() and captcha_server_key())


async def captcha_passed(token: str | None, ip: str) -> bool:
    """Yandex SmartCaptcha check; without keys there is no captcha. When Yandex
    cannot be reached the sign-up goes on (the IP limit still applies)."""
    if not captcha_enabled():
        return True
    if not token:
        return False
    url = (os.getenv("SMARTCAPTCHA_VALIDATE_URL") or "").strip() or CAPTCHA_VALIDATE_URL
    try:
        async with aiohttp.ClientSession(timeout=CAPTCHA_TIMEOUT) as session:
            async with session.post(
                url, data={"secret": captcha_server_key(), "token": token, "ip": ip}
            ) as response:
                if response.status >= 500:
                    LOGGER.warning("SmartCaptcha answered %s; letting the sign-up through", response.status)
                    return True
                payload = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        LOGGER.warning("SmartCaptcha is unreachable; letting the sign-up through", exc_info=True)
        return True
    return isinstance(payload, dict) and payload.get("status") == "ok"


# ---------------------------------------------------------------- consent
async def record_consent(user_id: uuid.UUID, versions: dict, ip: str) -> None:
    await _write(
        CONSENT_KEY.format(user_id=user_id),
        {**versions, "at": get_current_utc_datetime().isoformat(), "ip": ip},
    )
