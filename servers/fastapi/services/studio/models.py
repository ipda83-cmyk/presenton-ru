"""Image models offered by the Studio (arckep model ids)."""

from dataclasses import dataclass, field

GEMINI_ASPECT_RATIOS = ("1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16", "4:5", "5:4")
GPT_ASPECT_RATIOS = ("1:1", "3:2", "2:3")
RESOLUTIONS = ("1K", "2K", "4K")
QUALITY_LEVELS = ("draft", "standard", "high")


@dataclass(frozen=True)
class StudioModel:
    key: str
    title: str
    provider_id: str
    family: str  # "gemini" or "gpt"
    aspect_ratios: tuple[str, ...]
    resolutions: tuple[str, ...] = ()
    quality_levels: tuple[str, ...] = ()
    max_count: int = 1
    tags: tuple[str, ...] = field(default_factory=tuple)

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
        }


MODELS: dict[str, StudioModel] = {
    model.key: model
    for model in (
        StudioModel(
            key="nano_banana_2",
            title="Nano Banana 2",
            provider_id="gemini-3.1-flash-image",
            family="gemini",
            aspect_ratios=GEMINI_ASPECT_RATIOS,
            resolutions=RESOLUTIONS,
            tags=("balanced",),
        ),
        StudioModel(
            key="nano_banana_pro",
            title="Nano Banana Pro",
            provider_id="gemini-3-pro-image",
            family="gemini",
            aspect_ratios=GEMINI_ASPECT_RATIOS,
            resolutions=RESOLUTIONS,
            tags=("best",),
        ),
        StudioModel(
            key="chatgpt_images_2",
            title="ChatGPT Images 2",
            provider_id="gpt-image-2",
            family="gpt",
            aspect_ratios=GPT_ASPECT_RATIOS,
            quality_levels=QUALITY_LEVELS,
            max_count=4,
            tags=("text",),
        ),
    )
}
DEFAULT_MODEL = "nano_banana_2"

# gpt-image-2 takes a fixed size instead of an aspect ratio.
GPT_SIZES = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
}
GPT_QUALITY = {"draft": "low", "standard": "medium", "high": "high"}


def get_model(key: str | None) -> StudioModel | None:
    return MODELS.get((key or DEFAULT_MODEL).strip())
