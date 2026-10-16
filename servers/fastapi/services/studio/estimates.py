"""What one image costs us at arckep (POST {arckep}/images/estimate).

The answer is cached for a day per model and option ("<resolution>|<quality>")
in the key/value table "studio:estimates", together with arckep's raw answer
so the price can be checked. A failed estimate is retried after an hour.
"""

import asyncio
import logging
import time
from typing import Any

import aiohttp

from services.studio import catalog
from services.studio.models import GPT_SIZES, StudioModel

LOGGER = logging.getLogger(__name__)

ESTIMATES_KEY = "studio:estimates"
MAX_AGE_SECONDS = 24 * 60 * 60
FAILED_RETRY_SECONDS = 60 * 60
TIMEOUT = aiohttp.ClientTimeout(total=20, connect=10)
# Field names, best first, that may carry the cost in rubles.
COST_FIELDS = (
    "cost_rub",
    "price_rub",
    "total_rub",
    "amount_rub",
    "estimated_cost_rub",
    "estimated_price_rub",
    "rub",
    "cost",
    "price",
    "total",
    "amount",
    "estimated_cost",
    "estimated_price",
    "estimate",
)

_cache: dict[str, dict[str, dict]] | None = None
_primitives: tuple[asyncio.AbstractEventLoop, asyncio.Lock, asyncio.Semaphore] | None = None


def _loop_primitives() -> tuple[asyncio.Lock, asyncio.Semaphore]:
    """A lock for the cache and at most 4 estimates at once, per event loop."""
    global _primitives
    loop = asyncio.get_running_loop()
    if _primitives is None or _primitives[0] is not loop:
        _primitives = (loop, asyncio.Lock(), asyncio.Semaphore(4))
    return _primitives[1], _primitives[2]


def option_key(resolution: str | None, quality: str | None) -> str:
    return f"{resolution or ''}|{quality or ''}"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        try:
            number = float(value.replace(",", ".").replace("₽", "").strip())
        except ValueError:
            return None
        return number if number > 0 else None
    return None


def parse_cost(payload: Any, _depth: int = 0) -> float | None:
    """The cost in rubles from an estimate answer, wherever arckep put it."""
    if _depth > 4:
        return None
    number = _number(payload)
    if number is not None:
        return number
    if isinstance(payload, dict):
        for name in COST_FIELDS:
            if name in payload:
                found = parse_cost(payload[name], _depth + 1)
                if found is not None:
                    return found
        for value in payload.values():
            if isinstance(value, (dict, list)):
                found = parse_cost(value, _depth + 1)
                if found is not None:
                    return found
    if isinstance(payload, list):
        for value in payload:
            found = parse_cost(value, _depth + 1)
            if found is not None:
                return found
    return None


def estimate_body(model: StudioModel, resolution: str | None, quality: str | None) -> dict:
    body: dict[str, Any] = {"model": model.provider_id, "prompt": "price estimate", "n": 1}
    if model.family == "gpt":
        body["size"] = GPT_SIZES["1:1"]
    elif "1:1" in model.aspect_ratios:
        body["aspect_ratio"] = "1:1"
    if resolution:
        body["resolution"] = resolution
    if quality:
        body["quality"] = quality
    return body


async def _load_cache() -> dict[str, dict[str, dict]]:
    """One shared dict: estimates asked at once must not each load their own copy."""
    global _cache
    if _cache is None:
        lock, _ = _loop_primitives()
        async with lock:
            if _cache is None:
                stored = await catalog._read(ESTIMATES_KEY)
                _cache = stored if isinstance(stored, dict) else {}
    return _cache


async def _request(model: StudioModel, resolution: str | None, quality: str | None) -> tuple[float | None, Any]:
    from services.studio.service import studio_api_key, studio_base_url

    _, concurrency = _loop_primitives()
    async with concurrency:
        async with aiohttp.ClientSession(timeout=TIMEOUT, trust_env=True) as session:
            async with session.post(
                f"{studio_base_url()}/images/estimate",
                json=estimate_body(model, resolution, quality),
                headers={"Authorization": f"Bearer {studio_api_key()}"},
            ) as response:
                text = await response.text()
                try:
                    payload: Any = await response.json(content_type=None)
                except Exception:
                    payload = text[:500]
                if response.status >= 400:
                    return None, {"status": response.status, "body": payload}
                return parse_cost(payload), payload


async def cost(
    model: StudioModel, resolution: str | None, quality: str | None, *, refresh: bool = False
) -> float | None:
    """arckep's cost of one image, from the cache when it is fresh."""
    from services.studio.service import studio_configured

    key = option_key(resolution, quality)
    cache = await _load_cache()
    record = cache.get(model.key, {}).get(key)
    now = time.time()
    if record and not refresh:
        age = now - float(record.get("at") or 0)
        if record.get("cost") and age < MAX_AGE_SECONDS:
            return float(record["cost"])
        if not record.get("cost") and age < FAILED_RETRY_SECONDS:
            return None
    if not studio_configured():
        return float(record["cost"]) if record and record.get("cost") else None
    try:
        value, raw = await _request(model, resolution, quality)
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        value, raw = None, {"error": repr(error)[:200]}
    if value is None:
        LOGGER.warning("Studio estimate failed for %s %s: %s", model.key, key, str(raw)[:300])
    lock, _ = _loop_primitives()
    async with lock:
        cache.setdefault(model.key, {})[key] = {"cost": value, "raw": raw, "at": now}
        try:
            await catalog._write(ESTIMATES_KEY, cache)
        except Exception:
            LOGGER.warning("Could not save Studio estimates", exc_info=True)
    if value is None and record and record.get("cost"):
        return float(record["cost"])  # an older answer beats none
    return value


def cached_costs(model: StudioModel) -> dict[str, dict]:
    """What is known without asking arckep (for the admin page)."""
    return dict((_cache or {}).get(model.key, {}))


def reset_cache_for_tests() -> None:
    global _cache
    _cache = None
