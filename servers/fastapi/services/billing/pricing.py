"""Prices in whole rubles.

Studio image = cost of one image at arckep x markup x images, rounded up once.
The cost comes, in this order, from the administrator's manual cost for the
model (Admin → Models), arckep's estimate (POST /images/estimate, cached for a
day) or the costs measured for the first Studio models. The markup (1.45 by
default, per model if set) covers infrastructure, storage, YooKassa acquiring
(~3.5%) and profit. A presentation costs a fixed price per slide (settings),
slide pictures included.
"""

import asyncio
import math

from services.billing import settings
from services.studio import estimates
from services.studio.models import REGISTRY, StudioModel, enabled_models

# Measured arckep costs (09.2026), for when an estimate is not available.
KNOWN_COSTS_RUB = {
    "gemini-3.1-flash-image": {"1K": 8.13, "2K": 12.26, "4K": 18.33},
    "gemini-3-pro-image": {"1K": 17.0, "2K": 17.0, "4K": 26.56},
    "gpt-image-2": {"low": 1.0, "medium": 7.0, "high": 26.0},
}


class PriceUnknown(Exception):
    """Neither a manual cost nor an estimate is available for the model."""


def _rubles(value: float) -> int:
    # round() first: 8.13 * 1.45 must not become 11.788500000000001 -> 12 by accident.
    return max(1, math.ceil(round(value, 6)))


def options(model: StudioModel) -> list[tuple[str | None, str | None]]:
    """Every (resolution, quality) a user can pick for the model."""
    resolutions = list(model.resolutions) or [None]
    qualities = list(model.quality_levels) or [None]
    return [(resolution, quality) for resolution in resolutions for quality in qualities]


async def unit_cost(model: StudioModel, resolution: str | None, quality: str | None) -> float | None:
    option = estimates.option_key(resolution, quality)
    manual = REGISTRY.manual_cost(model, option) or REGISTRY.manual_cost(model, "*")
    if manual:
        return manual
    estimated = await estimates.cost(model, resolution, quality)
    if estimated:
        return estimated
    known = KNOWN_COSTS_RUB.get(model.provider_id, {})
    return known.get(resolution or "") or known.get(quality or "")


async def unit_price(model: StudioModel, resolution: str | None, quality: str | None) -> float | None:
    """One image with the markup, not rounded (the total is rounded once)."""
    cost = await unit_cost(model, model.resolve_resolution(resolution), model.resolve_quality(quality))
    return None if cost is None else round(cost * REGISTRY.markup(model), 4)


async def image_price(
    model: StudioModel,
    *,
    resolution: str | None = None,
    quality: str | None = None,
    count: int = 1,
) -> int:
    """One request: `count` images of `model` (edits and storyboard views count as one)."""
    unit = await unit_price(model, resolution, quality)
    if unit is None:
        raise PriceUnknown(model.key)
    return _rubles(unit * max(1, min(count, model.max_count)))


def presentation_price(slides: int) -> int:
    return max(0, slides) * settings.price_per_slide()


async def price_table() -> dict:
    """Per enabled model: the price of one image per "<resolution>|<quality>".

    The page multiplies by the number of images and rounds up, as image_price does.
    """

    async def model_units(model: StudioModel) -> tuple[str, dict]:
        units = {}
        for resolution, quality in options(model):
            unit = await unit_price(model, resolution, quality)
            if unit is not None:
                units[estimates.option_key(resolution, quality)] = unit
        return model.key, {"units": units}

    tables = await asyncio.gather(*(model_units(model) for model in enabled_models()))
    return {"studio": dict(tables), "per_slide": settings.price_per_slide()}
