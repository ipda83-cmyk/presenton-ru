"""Admin → Models: which Studio image models users see, names, modes, prices.

Administrators only (the /api/v1/admin/ prefix is guarded by the session middleware).
"""

import asyncio
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.billing import pricing
from services.studio import catalog, estimates
from services.studio.models import MODES, REGISTRY, StudioModel
from utils.i18n import http_error

API_V1_ADMIN_STUDIO_ROUTER = APIRouter(prefix="/api/v1/admin/studio", tags=["Studio"])


class ModelSettings(BaseModel):
    enabled: bool = False
    title: Optional[str] = Field(default=None, max_length=80)
    order: int = 0
    modes: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    markup: Optional[float] = Field(default=None, gt=0, le=100)
    costs: Optional[dict[str, float]] = None


class StudioModelsSettings(BaseModel):
    default_model: str = Field(default="", max_length=128)
    markup: float = Field(default=1.45, gt=0, le=100)
    slide_image_model: str = Field(default="", max_length=128)
    models: dict[str, ModelSettings] = Field(default_factory=dict)


def _costs(model: StudioModel) -> dict[str, dict[str, Any]]:
    """Per option: the cost used for prices and where it comes from (no network)."""
    known = estimates.cached_costs(model)
    result = {}
    for resolution, quality in pricing.options(model):
        option = estimates.option_key(resolution, quality)
        manual = REGISTRY.manual_cost(model, option)
        record = known.get(option) or {}
        legacy = pricing.KNOWN_COSTS_RUB.get(model.provider_id, {})
        legacy_cost = legacy.get(resolution or "") or legacy.get(quality or "")
        if manual:
            cost, source = manual, "manual"
        elif record.get("cost"):
            cost, source = record["cost"], "estimate"
        elif legacy_cost:
            cost, source = legacy_cost, "known"
        else:
            cost, source = None, "none"
        result[option] = {
            "resolution": resolution,
            "quality": quality,
            "cost": cost,
            "source": source,
            "price": pricing._rubles(cost * REGISTRY.markup(model)) if cost else None,
            "estimated_at": record.get("at"),
            "estimate_raw": record.get("raw"),
        }
    return result


def _model_row(model: StudioModel) -> dict:
    item = REGISTRY.settings["models"].get(model.key) or {}
    return {
        **model.public(),
        "enabled": model.enabled,
        "order": model.order,
        "provider": next(
            (entry.get("provider") for entry in REGISTRY.catalog if entry["id"] == model.key), None
        ),
        "description": model.description,
        "supported_modes": list(model.supported_modes),
        "max_references": model.max_references,
        "markup": item.get("markup"),
        "manual_costs": item.get("costs") or {},
        "costs": _costs(model),
    }


def _state() -> dict:
    settings = REGISTRY.settings
    models = sorted(
        REGISTRY.all.values(),
        key=lambda model: (not model.enabled, model.order if model.enabled else 0, model.key),
    )
    return {
        "catalog": catalog.catalog_state(),
        "modes": list(MODES),
        "default_model": REGISTRY.default_key(),
        "markup": settings["markup"],
        "slide_image_model": settings["slide_image_model"],
        "models": [_model_row(model) for model in models],
    }


@API_V1_ADMIN_STUDIO_ROUTER.get("/models")
async def admin_studio_models():
    return _state()


@API_V1_ADMIN_STUDIO_ROUTER.put("/models")
async def admin_studio_models_save(body: StudioModelsSettings):
    known = {entry["id"] for entry in REGISTRY.catalog}
    unknown = [key for key in body.models if key not in known]
    if unknown:
        raise http_error(400, "err.studio.unknownModel", model=unknown[0])
    await catalog.save_settings(body.model_dump(exclude_none=True))
    return _state()


@API_V1_ADMIN_STUDIO_ROUTER.post("/catalog/refresh")
async def admin_studio_catalog_refresh():
    await catalog.load(refresh_catalog=True)
    return _state()


@API_V1_ADMIN_STUDIO_ROUTER.post("/models/{model_id}/estimate")
async def admin_studio_model_estimate(model_id: str):
    """Ask arckep for the cost of every option of the model again."""
    model = REGISTRY.get(model_id, include_disabled=True)
    if model is None:
        raise http_error(404, "err.studio.unknownModel", model=model_id)
    await asyncio.gather(
        *(estimates.cost(model, resolution, quality, refresh=True) for resolution, quality in pricing.options(model))
    )
    return _model_row(model)
