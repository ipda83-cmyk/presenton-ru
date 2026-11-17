"""The public offer and the personal data policy, edited in Admin → Documents.

Shown to anyone at /legal/offer and /legal/privacy (no sign-in); the date of
the version a user agreed to is kept with their consent.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from models.sql.key_value import KeyValueSqlModel
from services.database import async_session_maker
from utils.datetime_utils import get_current_utc_datetime

LOGGER = logging.getLogger(__name__)

DOCUMENTS = ("offer", "privacy")
KEY = "legal:{doc}"
MAX_TITLE = 200
MAX_BODY = 200_000


async def load(doc: str) -> dict:
    """{doc, title, body, updated_at}; an empty body means not filled in yet."""
    try:
        async with async_session_maker() as session:
            row = await session.scalar(
                select(KeyValueSqlModel).where(KeyValueSqlModel.key == KEY.format(doc=doc))
            )
    except SQLAlchemyError:
        LOGGER.warning("Could not read the document %s", doc, exc_info=True)
        row = None
    value: Any = row.value if row is not None else None
    value = value if isinstance(value, dict) else {}
    return {
        "doc": doc,
        "title": str(value.get("title") or "")[:MAX_TITLE],
        "body": str(value.get("body") or "")[:MAX_BODY],
        "updated_at": value.get("updated_at"),
    }


async def save(doc: str, title: str, body: str) -> dict:
    value = {
        "title": " ".join(str(title or "").split())[:MAX_TITLE],
        "body": str(body or "").replace("\r\n", "\n").strip()[:MAX_BODY],
        "updated_at": get_current_utc_datetime().isoformat(),
    }
    key = KEY.format(doc=doc)
    async with async_session_maker() as session:
        row = await session.scalar(select(KeyValueSqlModel).where(KeyValueSqlModel.key == key))
        if row is None:
            session.add(KeyValueSqlModel(key=key, value=value))
        else:
            row.value = value
        await session.commit()
    return {"doc": doc, **value}


async def versions() -> dict:
    """The dates of the current texts, kept with a user's consent."""
    return {doc: (await load(doc))["updated_at"] for doc in DOCUMENTS}


async def public_path(doc: str) -> str | None:
    """/legal/<doc> once the text is filled in."""
    return f"/legal/{doc}" if (await load(doc))["body"] else None
