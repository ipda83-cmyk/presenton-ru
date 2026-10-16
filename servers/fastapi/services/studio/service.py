"""Studio operations: create and edit images through arckep, store results.

Results are the owner's ImageAsset records (`extras.source == "studio"`), so
they show up among the generated images in the slide editor and need no new
table.
"""

import os
import uuid
from typing import Any, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.sql.image_asset import ImageAsset
from services.studio import imaging
from services.studio.arckep import DEFAULT_BASE_URL, ArckepImages
from services.studio.models import GPT_SIZES, StudioModel
from utils.asset_directory_utils import get_images_directory
from utils.get_env import (
    get_gemini_search_api_key_env,
    get_gemini_search_base_url_env,
    get_studio_api_key_env,
    get_studio_base_url_env,
)

STUDIO_SOURCE = "studio"
OPERATIONS = ("upscale", "remove_bg")
OPERATION_PROMPTS = {
    "upscale": (
        "Upscale and enhance this image to maximum quality: increase resolution and "
        "sharpness, restore fine details and textures, remove noise, blur and "
        "compression artifacts, keep the original composition, colors and content "
        "EXACTLY the same. Do not add or change any objects. Output a crisp, "
        "high-resolution version."
    ),
    "remove_bg": (
        "Remove the background completely. Keep ONLY the main subject, cut out cleanly "
        "along its edges. Place the subject on a fully transparent background. Output a "
        "PNG with an alpha channel. Do not change the subject itself."
    ),
}
MASKED_PROMPT = (
    "The second image is a mask: its transparent area marks the only region to "
    "change in the first image. Keep everything outside that region exactly as it "
    "is. Change requested: {prompt}"
)
REFERENCE_PROMPT = (
    "Use the last image as the reference object (logo, product or element). "
    "Insert it into the first image naturally, matching perspective, lighting and "
    "scale. {prompt}"
)


def studio_base_url() -> str:
    return (get_studio_base_url_env() or "").strip().rstrip("/") or DEFAULT_BASE_URL


def studio_api_key() -> str:
    """The Studio key, or the web search key when search goes through the same
    arckep host (one key for both, as given by the service)."""
    key = (get_studio_api_key_env() or "").strip()
    if key:
        return key
    search_base = (get_gemini_search_base_url_env() or "").strip()
    if search_base and urlparse(search_base).netloc == urlparse(studio_base_url()).netloc:
        return (get_gemini_search_api_key_env() or "").strip()
    return ""


def studio_configured() -> bool:
    return bool(studio_api_key())


def studio_client() -> ArckepImages:
    return ArckepImages(studio_base_url(), studio_api_key())


def generation_body(
    model: StudioModel,
    prompt: str,
    *,
    aspect_ratio: Optional[str] = None,
    resolution: Optional[str] = None,
    quality: Optional[str] = None,
    count: int = 1,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model.provider_id,
        "prompt": prompt.strip(),
        "n": max(1, min(count, model.max_count)),
    }
    if model.family == "gpt":
        if aspect_ratio in GPT_SIZES:
            body["size"] = GPT_SIZES[aspect_ratio]
    elif aspect_ratio in model.aspect_ratios:
        body["aspect_ratio"] = aspect_ratio
    if resolution in model.resolutions:
        body["resolution"] = resolution
    quality = model.resolve_quality(quality)
    if quality:
        body["quality"] = quality
    return body


async def create_images(
    model: StudioModel,
    prompt: str,
    *,
    aspect_ratio: Optional[str] = None,
    resolution: Optional[str] = None,
    quality: Optional[str] = None,
    count: int = 1,
    client: Optional[ArckepImages] = None,
) -> list[bytes]:
    body = generation_body(
        model, prompt, aspect_ratio=aspect_ratio, resolution=resolution, quality=quality, count=count
    )
    images = await (client or studio_client()).generate(body)
    return [imaging.png_bytes(image) for image in images]


def edit_prompt(prompt: str, *, masked: bool, operation: Optional[str], reference: bool) -> str:
    if operation:
        return OPERATION_PROMPTS[operation]
    text = prompt.strip()
    if reference:
        text = REFERENCE_PROMPT.format(prompt=text).strip()
    if masked:
        text = MASKED_PROMPT.format(prompt=text)
    return text


async def edit_image(
    model: StudioModel,
    source: bytes,
    prompt: str = "",
    *,
    mask: Optional[bytes] = None,
    reference: Optional[bytes] = None,
    operation: Optional[str] = None,
    resolution: Optional[str] = None,
    quality: Optional[str] = None,
    client: Optional[ArckepImages] = None,
) -> bytes:
    original = imaging.png_bytes(source)
    width, height = imaging.image_size(original)
    send = original
    body: dict[str, Any] = {
        "model": model.provider_id,
        "prompt": edit_prompt(prompt, masked=mask is not None, operation=operation, reference=reference is not None),
        "n": 1,
    }
    if model.family == "gpt":
        # gpt-image-2 only returns fixed sizes and drifts without one.
        size_name, size = imaging.pick_gpt_size(width, height)
        send = imaging.resize_png(original, size)
        body["size"] = size_name
    elif resolution in model.resolutions:
        body["resolution"] = resolution
    quality = model.resolve_quality(quality)
    if quality:
        body["quality"] = quality

    main = imaging.fit_for_upload(send)
    references = [main]
    if mask is not None:
        # Same size as the uploaded image so the hint lines up with it.
        references.append(imaging.resize_png(mask, imaging.image_size(main)))
    if reference is not None:
        references.append(imaging.fit_for_upload(reference))

    results = await (client or studio_client()).generate(body, references)
    result = imaging.png_bytes(results[0])
    if mask is not None:
        # Outside the brushed area the original stays pixel-exact.
        return imaging.compose_masked(original, result, mask)
    return result


async def save_studio_image(
    session: AsyncSession, png: bytes, extras: dict[str, Any]
) -> ImageAsset:
    path = os.path.join(get_images_directory(), f"studio-{uuid.uuid4().hex}.png")
    with open(path, "wb") as file:
        file.write(png)
    asset = ImageAsset(path=path, is_uploaded=False, extras={"source": STUDIO_SOURCE, **extras})
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return asset


async def studio_history(session: AsyncSession, limit: int = 60) -> list[ImageAsset]:
    """The owner's Studio images, newest first (owner scoping is automatic)."""
    rows = await session.scalars(
        select(ImageAsset)
        .where(ImageAsset.is_uploaded == False)  # noqa: E712 (SQL expression)
        .order_by(ImageAsset.created_at.desc())
        .limit(limit * 4)
    )
    studio = [row for row in rows if (row.extras or {}).get("source") == STUDIO_SOURCE]
    return studio[:limit]
