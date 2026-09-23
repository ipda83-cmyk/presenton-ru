"""Per-user interface language.

The UI language preference (``ru``, ``en`` or ``auto`` = follow the browser)
lives in the NEXT_LOCALE cookie (read by both the Next.js frontend and
utils.i18n.LocaleMiddleware). For signed-in users the choice is
also stored server-side so it follows them to other browsers: resolution is
profile -> cookie -> default. The profile value is applied at login by
re-issuing the cookie.

It is kept in the generic key/value table (one row per user) instead of a
column on ``user``: the auth model is loaded on every request, and a column
that is missing because migrations were not run would break sign-in for
everyone.
"""

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from models.sql.key_value import KeyValueSqlModel
from utils.i18n import LOCALE_COOKIE, normalize_preference

LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
logger = logging.getLogger(__name__)


def user_locale_key(user_id: uuid.UUID | str) -> str:
    return f"ui_locale:{user_id}"


# Language persistence is a convenience: a storage failure must never break
# sign-in or the status endpoint, so errors are logged and swallowed.


async def get_user_locale(
    session: AsyncSession, user_id: uuid.UUID | str
) -> str | None:
    try:
        row = await session.scalar(
            select(KeyValueSqlModel).where(
                KeyValueSqlModel.key == user_locale_key(user_id)
            )
        )
    except SQLAlchemyError:
        logger.warning("Could not read the saved interface language", exc_info=True)
        await session.rollback()
        return None
    if row is None or not isinstance(row.value, dict):
        return None
    value = row.value.get("locale")
    return normalize_preference(value) if isinstance(value, str) else None


async def set_user_locale(
    session: AsyncSession, user_id: uuid.UUID | str, locale: str
) -> None:
    key = user_locale_key(user_id)
    try:
        row = await session.scalar(
            select(KeyValueSqlModel).where(KeyValueSqlModel.key == key)
        )
        if row is None:
            session.add(KeyValueSqlModel(key=key, value={"locale": locale}))
        else:
            row.value = {"locale": locale}
        await session.commit()
    except SQLAlchemyError:
        logger.warning("Could not save the interface language", exc_info=True)
        await session.rollback()


async def delete_user_locale(session: AsyncSession, user_id: uuid.UUID | str) -> None:
    await session.execute(
        delete(KeyValueSqlModel).where(KeyValueSqlModel.key == user_locale_key(user_id))
    )


def set_locale_cookie(response: Response, locale: str, *, secure: bool) -> None:
    # Readable by the frontend (next-intl reads it server-side, the switcher
    # client-side), so not HttpOnly.
    response.set_cookie(
        LOCALE_COOKIE,
        locale,
        max_age=LOCALE_COOKIE_MAX_AGE,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )
