"""Image models of the Studio: arckep's catalog plus the administrator's choice.

The catalog (GET {arckep}/models, type "image") says what each model can do:
aspect ratios, resolutions, quality levels, how many images and references.
The administrator picks which models users see, under which name, in which
order and modes, the markup and the model for slide pictures (Admin → Models).

Everything here is synchronous and in memory: services/studio/catalog.py loads
the catalog and the settings from the database at startup and after every save.
"""

from dataclasses import dataclass, field
import json
import os
from typing import Any

CATALOG_SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "catalog_snapshot.json")

MODES = ("generate", "edit", "reference", "storyboard")
MAX_COUNT = 4  # images per request the Studio offers
DEFAULT_MARKUP = 1.45
DEFAULT_MODEL = "gemini-nano-banana-2.1"
# Who the slide pictures show (the product is for a Russian audience); empty = say nothing.
DEFAULT_PEOPLE_APPEARANCE = "Slavic (Eastern European, Russian) appearance"
PEOPLE_APPEARANCE_MAX = 300

# Keys of the first Studio version (history, old clients).
LEGACY_KEYS = {
    "nano_banana_2": "gemini-nano-banana-2.1",
    "nano_banana_pro": "gemini-3-pro-image",
    "chatgpt_images_2": "gpt-image-2",
}

# The starting set (16.10.2026): everything else is off until the administrator turns it on.
DEFAULT_ENABLED: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("gemini-nano-banana-2.1", "Nano Banana 2.1", ("balanced",)),
    ("gemini-3-pro-image", "Nano Banana Pro", ("best",)),
    ("gpt-image-2.5-sunburst", "ChatGPT Images 2.5", ("text",)),
    ("flux-2-pro", "FLUX.2 Pro", ()),
    ("seedream-5.0-pro", "Seedream 5.0 Pro", ()),
    ("recraft-v4.1-vector", "Recraft V4.1 Vector", ("vector",)),
)

# gpt-image models take a fixed size instead of an aspect ratio.
GPT_SIZES = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
}
# Quality names of the first Studio version.
GPT_QUALITY = {"draft": "low", "standard": "medium", "high": "high"}


@dataclass(frozen=True)
class StudioModel:
    key: str
    title: str
    provider_id: str
    family: str  # "gemini", "gpt" or the catalog provider
    aspect_ratios: tuple[str, ...]
    resolutions: tuple[str, ...] = ()
    quality_levels: tuple[str, ...] = ()
    max_count: int = 1
    tags: tuple[str, ...] = field(default_factory=tuple)
    modes: tuple[str, ...] = ("generate",)
    supported_modes: tuple[str, ...] = ("generate",)
    max_references: int | None = None
    enabled: bool = True
    order: int = 0
    description: str = ""

    def public(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "family": self.family,
            "aspect_ratios": list(self.aspect_ratios),
            "resolutions": list(self.resolutions),
            "quality_levels": list(self.quality_levels),
            "max_count": self.max_count,
            "tags": list(self.tags),
            "modes": list(self.modes),
        }

    def resolve_quality(self, quality: str | None) -> str | None:
        """The catalog's quality level for a requested one (old names accepted)."""
        if not self.quality_levels:
            return None
        if quality in self.quality_levels:
            return quality
        mapped = GPT_QUALITY.get(quality or "")
        if mapped in self.quality_levels:
            return mapped
        return "medium" if "medium" in self.quality_levels else self.quality_levels[0]

    def resolve_resolution(self, resolution: str | None) -> str | None:
        if not self.resolutions:
            return None
        if resolution in self.resolutions:
            return resolution
        return "1K" if "1K" in self.resolutions else self.resolutions[0]


def family_of(provider: str | None) -> str:
    if provider == "gemini":
        return "gemini"
    if provider == "openai_image":
        return "gpt"
    return provider or "other"


def supported_modes(entry: dict) -> tuple[str, ...]:
    """What the Studio can do with a catalog model.

    A plain edit sends the picture (1 reference), the brush adds the mask (2),
    "insert an object" adds the object (3). The storyboard keeps a character
    only on Gemini models, so it is offered there by default.
    """
    modes = set(entry.get("modes") or ())
    references = entry.get("max_reference_images")
    refs = 99 if references is None else int(references)
    result = []
    if "generate" in modes and not entry.get("requires_reference_image"):
        result.append("generate")
    can_edit = "edit" in modes or "edit_with_reference" in modes
    if can_edit and refs >= 2:
        result.append("edit")
    if can_edit and refs >= 3:
        result.append("reference")
    if can_edit and refs >= 1:
        result.append("storyboard")
    return tuple(result)


def default_modes(entry: dict) -> tuple[str, ...]:
    supported = supported_modes(entry)
    if family_of(entry.get("provider")) != "gemini":
        supported = tuple(mode for mode in supported if mode != "storyboard")
    return supported


def load_snapshot() -> list[dict]:
    with open(CATALOG_SNAPSHOT_PATH, encoding="utf-8") as handle:
        return list(json.load(handle)["models"])


def default_settings() -> dict:
    return {
        "default_model": DEFAULT_MODEL,
        "markup": DEFAULT_MARKUP,
        "slide_image_model": "",
        "people_appearance": DEFAULT_PEOPLE_APPEARANCE,
        "models": {
            model_id: {"enabled": True, "title": title, "order": index, "tags": list(tags)}
            for index, (model_id, title, tags) in enumerate(DEFAULT_ENABLED)
        },
    }


def _float(value: Any, default: float | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def normalize_settings(raw: Any, catalog_ids: set[str]) -> dict:
    """Settings from the database or the admin form, cleaned up."""
    base = default_settings()
    raw = raw if isinstance(raw, dict) else {}
    result = {
        "default_model": str(raw.get("default_model") or base["default_model"]),
        "markup": min(_float(raw.get("markup"), DEFAULT_MARKUP) or DEFAULT_MARKUP, 100.0),
        "slide_image_model": str(raw.get("slide_image_model") or ""),
        "people_appearance": " ".join(
            str(raw.get("people_appearance", base["people_appearance"]) or "").split()
        )[:PEOPLE_APPEARANCE_MAX],
        "models": {},
    }
    models = raw.get("models") if isinstance(raw.get("models"), dict) else base["models"]
    for model_id, item in models.items():
        if model_id not in catalog_ids or not isinstance(item, dict):
            continue
        clean: dict[str, Any] = {"enabled": bool(item.get("enabled"))}
        title = " ".join(str(item.get("title") or "").split())[:80]
        if title:
            clean["title"] = title
        try:
            clean["order"] = int(item.get("order", 0))
        except (TypeError, ValueError):
            clean["order"] = 0
        if isinstance(item.get("modes"), list):
            clean["modes"] = [mode for mode in item["modes"] if mode in MODES]
        if isinstance(item.get("tags"), list):
            clean["tags"] = [str(tag)[:32] for tag in item["tags"]][:4]
        markup = _float(item.get("markup"), None)
        if markup is not None:
            clean["markup"] = min(markup, 100.0)
        if isinstance(item.get("costs"), dict):
            costs = {
                str(option)[:64]: cost
                for option, value in item["costs"].items()
                if (cost := _float(value, None)) is not None
            }
            if costs:
                clean["costs"] = costs
        result["models"][model_id] = clean
    if result["slide_image_model"] not in catalog_ids:
        result["slide_image_model"] = ""
    return result


def build_model(entry: dict, item: dict | None) -> StudioModel:
    item = item or {}
    supported = supported_modes(entry)
    chosen = item.get("modes")
    modes = tuple(mode for mode in (chosen if chosen is not None else default_modes(entry)) if mode in supported)
    references = entry.get("max_reference_images")
    return StudioModel(
        key=entry["id"],
        title=item.get("title") or entry.get("name") or entry["id"],
        provider_id=entry["id"],
        family=family_of(entry.get("provider")),
        aspect_ratios=tuple(entry.get("aspect_ratios") or ("1:1",)),
        resolutions=tuple(entry.get("resolutions") or ()),
        quality_levels=tuple(entry.get("quality_levels") or ()),
        max_count=max(1, min(int(entry.get("max_images") or 1), MAX_COUNT)),
        tags=tuple(item.get("tags") or ()),
        modes=modes,
        supported_modes=supported,
        max_references=None if references is None else int(references),
        enabled=bool(item.get("enabled")),
        order=int(item.get("order", 0)),
        description=str(entry.get("description") or ""),
    )


class Registry:
    def __init__(self, catalog: list[dict], settings: Any = None):
        self.apply(catalog, settings)

    def apply(self, catalog: list[dict], settings: Any = None) -> None:
        self.catalog = [entry for entry in catalog if isinstance(entry, dict) and entry.get("id")]
        ids = {entry["id"] for entry in self.catalog}
        self.settings = normalize_settings(settings if settings is not None else default_settings(), ids)
        items = self.settings["models"]
        self.all = {entry["id"]: build_model(entry, items.get(entry["id"])) for entry in self.catalog}
        self.enabled = sorted(
            (model for model in self.all.values() if model.enabled),
            key=lambda model: (model.order, model.title.lower()),
        )

    def resolve_key(self, key: str | None) -> str:
        key = (key or "").strip()
        return LEGACY_KEYS.get(key, key)

    def get(self, key: str | None, *, include_disabled: bool = False) -> StudioModel | None:
        key = self.resolve_key(key) or self.default_key()
        model = self.all.get(key)
        if model is None or (not model.enabled and not include_disabled):
            return None
        return model

    def default_key(self) -> str:
        wanted = self.settings["default_model"]
        if wanted in self.all and self.all[wanted].enabled:
            return wanted
        return self.enabled[0].key if self.enabled else ""

    def markup(self, model: StudioModel) -> float:
        item = self.settings["models"].get(model.key) or {}
        return float(item.get("markup") or self.settings["markup"])

    def manual_cost(self, model: StudioModel, option: str) -> float | None:
        item = self.settings["models"].get(model.key) or {}
        costs = item.get("costs") or {}
        return costs.get(option)

    def people_appearance(self) -> str:
        return self.settings.get("people_appearance", "")

    def slide_image_model(self) -> StudioModel | None:
        key = self.settings["slide_image_model"]
        return self.all.get(key) if key else None


REGISTRY = Registry(load_snapshot())


def get_model(key: str | None, *, include_disabled: bool = False) -> StudioModel | None:
    return REGISTRY.get(key, include_disabled=include_disabled)


def enabled_models() -> list[StudioModel]:
    return list(REGISTRY.enabled)


def default_model_key() -> str:
    return REGISTRY.default_key()
