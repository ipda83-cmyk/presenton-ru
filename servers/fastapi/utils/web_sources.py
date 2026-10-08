"""Web pages a presentation's outline was researched from.

Shown next to the outline so users can see where the facts came from. Kept in
the generic key/value table (one row per presentation) instead of a column on
``presentations``: a column that is missing because migrations were not run
would break every presentation query, while a missing row only means "no
sources". Storage is best effort for the same reason.
"""

import logging
import uuid
from typing import Any, Iterable
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from models.sql.key_value import KeyValueSqlModel
from utils.datetime_utils import get_current_utc_datetime

LOGGER = logging.getLogger(__name__)

SNIPPET_MAX_CHARS = 400
TITLE_MAX_CHARS = 200
WEB_SOURCE_STATUSES = frozenset(
    {"ok", "empty", "failed", "native", "unavailable", "disabled", "none"}
)


def web_sources_key(presentation_id: uuid.UUID | str) -> str:
    return f"web_sources:{presentation_id}"


def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _truncate(value: str, limit: int) -> str:
    value = " ".join(str(value or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def build_web_sources_record(
    status: str,
    provider: str | None = None,
    query: str | None = None,
    results: Iterable[Any] = (),
) -> dict:
    """Serializable record; results need ``title``, ``url`` and ``snippet``."""
    sources = []
    seen_urls: set[str] = set()
    for result in results:
        url = str(getattr(result, "url", "") or "").strip()
        # Only real web pages: the URL is rendered as a link in the browser.
        if urlparse(url).scheme not in ("http", "https") or not _domain(url):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        domain = str(getattr(result, "domain", "") or "").strip().lower()
        if domain.startswith("www."):
            domain = domain[4:]
        sources.append(
            {
                "title": _truncate(getattr(result, "title", ""), TITLE_MAX_CHARS),
                "url": url,
                "domain": domain or _domain(url),
                "snippet": _truncate(getattr(result, "snippet", ""), SNIPPET_MAX_CHARS),
            }
        )
    return {
        "status": status if status in WEB_SOURCE_STATUSES else "failed",
        "provider": provider,
        "query": query,
        "sources": sources,
        "updated_at": get_current_utc_datetime().isoformat(),
    }


async def save_web_sources(
    session: AsyncSession, presentation_id: uuid.UUID | str, record: dict
) -> None:
    key = web_sources_key(presentation_id)
    try:
        row = await session.scalar(
            select(KeyValueSqlModel).where(KeyValueSqlModel.key == key)
        )
        if row is None:
            session.add(KeyValueSqlModel(key=key, value=record))
        else:
            row.value = record
        await session.commit()
    except SQLAlchemyError:
        LOGGER.warning("Could not save web sources", exc_info=True)
        await session.rollback()


async def get_web_sources(
    session: AsyncSession, presentation_id: uuid.UUID | str
) -> dict | None:
    try:
        row = await session.scalar(
            select(KeyValueSqlModel).where(
                KeyValueSqlModel.key == web_sources_key(presentation_id)
            )
        )
    except SQLAlchemyError:
        LOGGER.warning("Could not read web sources", exc_info=True)
        await session.rollback()
        return None
    if row is None or not isinstance(row.value, dict):
        return None
    return row.value


async def delete_web_sources(
    session: AsyncSession, presentation_id: uuid.UUID | str
) -> None:
    """Best effort, after the presentation itself is committed."""
    try:
        await session.execute(
            delete(KeyValueSqlModel).where(
                KeyValueSqlModel.key == web_sources_key(presentation_id)
            )
        )
        await session.commit()
    except SQLAlchemyError:
        LOGGER.warning("Could not delete web sources", exc_info=True)
        await session.rollback()
