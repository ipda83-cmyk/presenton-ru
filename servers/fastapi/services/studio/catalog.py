"""Loading arckep's model catalog and the administrator's model settings.

Both live in the key/value table: "studio:catalog" (the image models of
GET {arckep}/models, refreshed once a day or on demand) and "studio:models"
(the settings, see services/studio/models.py). Without arckep the bundled
snapshot is used, so the Studio and the admin page always have a catalog.
"""

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from models.sql.key_value import KeyValueSqlModel
from services.studio import models as registry
from utils.datetime_utils import get_current_utc_datetime

LOGGER = logging.getLogger(__name__)

CATALOG_KEY = "studio:catalog"
SETTINGS_KEY = "studio:models"
CATALOG_MAX_AGE_SECONDS = 24 * 60 * 60
FETCH_TIMEOUT = aiohttp.ClientTimeout(total=20, connect=10)
CATALOG_FIELDS = (
    "id",
    "name",
    "provider",
    "modes",
    "aspect_ratios",
    "resolutions",
    "quality_levels",
    "max_images",
    "max_reference_images",
    "requires_reference_image",
    "features",
    "description",
)

_state: dict[str, Any] = {"catalog_fetched_at": 0.0, "catalog_source": "snapshot"}
_locks: dict[int, asyncio.Lock] = {}


def _lock() -> asyncio.Lock:
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _locks:
        _locks.clear()
        _locks[loop_id] = asyncio.Lock()
    return _locks[loop_id]


def _session_maker():
    from services.database import async_session_maker

    return async_session_maker


async def _read(key: str) -> Any:
    try:
        async with _session_maker()() as session:
            row = await session.scalar(select(KeyValueSqlModel).where(KeyValueSqlModel.key == key))
    except SQLAlchemyError:
        LOGGER.warning("Could not read %s", key, exc_info=True)
        return None
    return row.value if row is not None else None


async def _write(key: str, value: dict) -> None:
    async with _session_maker()() as session:
        row = await session.scalar(select(KeyValueSqlModel).where(KeyValueSqlModel.key == key))
        if row is None:
            session.add(KeyValueSqlModel(key=key, value=value))
        else:
            row.value = value
        await session.commit()


def image_models_from_catalog(payload: Any) -> list[dict]:
    """The image models of a GET /models answer ({"data": [...]} or a bare list)."""
    items = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [
        {field: item.get(field) for field in CATALOG_FIELDS}
        for item in items
        if isinstance(item, dict) and item.get("id") and item.get("type") == "image"
    ]


async def fetch_catalog() -> list[dict]:
    """Image models from arckep; raises on any failure."""
    from services.studio.service import studio_api_key, studio_base_url

    async with aiohttp.ClientSession(timeout=FETCH_TIMEOUT, trust_env=True) as session:
        async with session.get(
            f"{studio_base_url()}/models",
            headers={"Authorization": f"Bearer {studio_api_key()}"},
        ) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}: {text[:200]}")
    models = image_models_from_catalog(json.loads(text))
    if not models:
        raise RuntimeError("the catalog has no image models")
    return models


async def load(*, refresh_catalog: bool = False) -> None:
    """Apply the stored catalog and settings; refresh the catalog when it is old."""
    from services.studio.service import studio_configured

    async with _lock():
        stored = await _read(CATALOG_KEY)
        catalog = registry.load_snapshot()
        fetched_at = 0.0
        source = "snapshot"
        if isinstance(stored, dict) and isinstance(stored.get("models"), list) and stored["models"]:
            catalog = stored["models"]
            fetched_at = float(stored.get("fetched_at") or 0)
            source = "arckep"
        if studio_configured() and (refresh_catalog or time.time() - fetched_at > CATALOG_MAX_AGE_SECONDS):
            try:
                catalog = await fetch_catalog()
                fetched_at = time.time()
                source = "arckep"
                await _write(
                    CATALOG_KEY,
                    {"models": catalog, "fetched_at": fetched_at, "updated_at": get_current_utc_datetime().isoformat()},
                )
                LOGGER.info("Studio catalog refreshed: %d image models", len(catalog))
                _state.pop("catalog_error", None)
            except Exception as error:  # keep what we have
                LOGGER.warning("Studio catalog refresh failed: %s", error)
                _state["catalog_error"] = str(error)[:300]
        settings = await _read(SETTINGS_KEY)
        registry.REGISTRY.apply(catalog, settings if isinstance(settings, dict) else None)
        _state.update(catalog_fetched_at=fetched_at, catalog_source=source)


async def save_settings(raw: dict) -> dict:
    ids = {entry["id"] for entry in registry.REGISTRY.catalog}
    settings = registry.normalize_settings(raw, ids)
    await _write(SETTINGS_KEY, settings)
    async with _lock():
        registry.REGISTRY.apply(registry.REGISTRY.catalog, settings)
    return settings


def catalog_state() -> dict:
    return {
        "source": _state["catalog_source"],
        "fetched_at": _state["catalog_fetched_at"] or None,
        "error": _state.get("catalog_error"),
        "count": len(registry.REGISTRY.catalog),
    }


_background: set[asyncio.Task] = set()


def _in_background(coroutine) -> None:
    task = asyncio.create_task(coroutine)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _warm_prices() -> None:
    from services.billing.pricing import price_table

    try:
        await price_table()
    except Exception:
        LOGGER.warning("Could not warm Studio prices", exc_info=True)


async def startup() -> None:
    """Catalog and settings at start; prices are asked from arckep in the background."""
    try:
        await load()
    except Exception:
        LOGGER.warning("Could not load Studio models; using the bundled catalog", exc_info=True)
    _in_background(_warm_prices())


def ensure_fresh() -> None:
    """Refresh a day-old catalog without making the caller wait."""
    from services.studio.service import studio_configured

    if not studio_configured() or _background:
        return
    if time.time() - (_state["catalog_fetched_at"] or 0) > CATALOG_MAX_AGE_SECONDS:
        _in_background(load())
