"""Prices in whole rubles, as in the standalone AI Image Studio.

Price = arckep cost x MARGIN, rounded up. The margin covers infrastructure,
storage, YooKassa acquiring (~3.5%) and profit. Costs (arckep estimates, 09.2026):
  Nano Banana 2   1K 8.13 / 2K 12.26 / 4K 18.33
  Nano Banana Pro 1K 17.0 / 2K 17.0 / 4K 26.56
  ChatGPT Images 2 by quality: draft 1 / standard 7 / high 26
A presentation costs a fixed price per slide (settings), slide pictures included.
"""

import math

from services.billing import settings
from services.studio.models import MODELS, StudioModel

MARGIN = 1.45

GEMINI_COST_RUB = {"nano_banana_2": 8.13, "nano_banana_pro": 17.0}
RESOLUTION_MULTIPLIER = {
    "nano_banana_2": {"1K": 1.0, "2K": 1.51, "4K": 2.25},
    "nano_banana_pro": {"1K": 1.0, "2K": 1.0, "4K": 1.56},
}
GPT_COST_RUB = {"draft": 1.0, "standard": 7.0, "high": 26.0}


def _rubles(value: float) -> int:
    # round() first: 8.13 * 1.45 must not become 11.788500000000001 -> 12 by accident.
    return max(1, math.ceil(round(value, 6)))


def image_price(
    model: StudioModel,
    *,
    resolution: str | None = None,
    quality: str | None = None,
    count: int = 1,
) -> int:
    """One request: `count` images of `model` (edits and storyboard views count as one)."""
    count = max(1, min(count, model.max_count))
    if model.family == "gpt":
        unit = GPT_COST_RUB.get(quality or "standard", GPT_COST_RUB["standard"]) * MARGIN
    else:
        multipliers = RESOLUTION_MULTIPLIER.get(model.key, RESOLUTION_MULTIPLIER["nano_banana_2"])
        cost = GEMINI_COST_RUB.get(model.key, GEMINI_COST_RUB["nano_banana_2"])
        unit = cost * multipliers.get(resolution or "1K", 1.0) * MARGIN
    return _rubles(unit * count)


def presentation_price(slides: int) -> int:
    return max(0, slides) * settings.price_per_slide()


def price_table() -> dict:
    """Per model: price of one image by resolution (Gemini) or quality (GPT)."""
    table = {}
    for model in MODELS.values():
        if model.family == "gpt":
            table[model.key] = {"quality": {level: image_price(model, quality=level) for level in model.quality_levels}}
        else:
            table[model.key] = {"resolution": {res: image_price(model, resolution=res) for res in model.resolutions}}
    return {"studio": table, "per_slide": settings.price_per_slide()}
