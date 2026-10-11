"""The user's own photos placed on outline slides (AI Image Studio, step 3.3).

Photos attached on the create page are saved as the user's images; once the
outline exists a vision-capable text model assigns each photo to the slide it
illustrates (the user can move them on the outline page). On prepare, slides
with a photo get a layout with an image slot, and generation puts the photo
there instead of a generated picture.

Stored in the generic key/value table, one row per presentation, like the web
sources: no migration, and a missing row only means "no photos".
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import uuid
from typing import Any, Iterable, Optional, Sequence

from llmai import get_client
from llmai.shared import ImageContentPart, JSONSchemaResponse, SystemMessage, UserMessage
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from models.presentation_layout import PresentationLayoutModel
from models.presentation_outline_model import PresentationOutlineModel, SlideOutlineModel
from models.presentation_structure_model import PresentationStructureModel
from models.sql.key_value import KeyValueSqlModel
from utils.asset_directory_utils import resolve_image_path_to_filesystem
from utils.datetime_utils import get_current_utc_datetime
from utils.llm_config import get_llm_config
from utils.llm_provider import get_model
from utils.llm_utils import generate_structured_with_schema_retries

LOGGER = logging.getLogger(__name__)

MAX_PHOTOS = 20
NAME_MAX_CHARS = 120
MATCH_IMAGE_SIDE = 640
MATCH_TIMEOUT_SECONDS = 120
SLIDE_SUMMARY_CHARS = 400
# How an assignment came about: by the model, by order (no vision), by the user.
MATCH_METHODS = frozenset({"vision", "order", "manual"})
IMAGE_SLOT_KEYS = frozenset({"image_prompt", "__image_prompt__"})
PHOTO_HINT = "![The user's own photo goes on this slide](user-photo)"


def slide_photos_key(presentation_id: uuid.UUID | str) -> str:
    return f"slide_photos:{presentation_id}"


# --- record -----------------------------------------------------------------


def _slide_index(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def normalize_photos(raw: Iterable[Any], *, check_files: bool = True) -> list[dict]:
    """Keep well-formed entries pointing at the user's own images."""
    photos: list[dict] = []
    seen: set[str] = set()
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen or url.startswith("data:"):
            continue
        if check_files and not resolve_image_path_to_filesystem(url):
            continue
        seen.add(url)
        name = " ".join(str(item.get("name") or os.path.basename(url)).split())[:NAME_MAX_CHARS]
        photos.append({"url": url, "name": name, "slide": _slide_index(item.get("slide"))})
        if len(photos) >= MAX_PHOTOS:
            break
    return photos


def build_record(photos: list[dict], matched: Optional[str]) -> dict:
    return {
        "photos": photos,
        "matched": matched if matched in MATCH_METHODS else None,
        "updated_at": get_current_utc_datetime().isoformat(),
    }


def photos_by_slide(record: Optional[dict], n_slides: int) -> list[list[str]]:
    """Photo URLs per outline slide, in the order they were listed."""
    per_slide: list[list[str]] = [[] for _ in range(max(0, n_slides))]
    for photo in (record or {}).get("photos") or []:
        slide = _slide_index(photo.get("slide")) if isinstance(photo, dict) else None
        if slide is not None and slide < n_slides and photo.get("url"):
            per_slide[slide].append(photo["url"])
    return per_slide


async def get_slide_photos(session: AsyncSession, presentation_id: uuid.UUID | str) -> Optional[dict]:
    try:
        row = await session.scalar(
            select(KeyValueSqlModel).where(KeyValueSqlModel.key == slide_photos_key(presentation_id))
        )
    except SQLAlchemyError:
        LOGGER.warning("Could not read slide photos", exc_info=True)
        await session.rollback()
        return None
    if row is None or not isinstance(row.value, dict):
        return None
    return row.value


async def save_slide_photos(session: AsyncSession, presentation_id: uuid.UUID | str, record: dict) -> None:
    key = slide_photos_key(presentation_id)
    try:
        row = await session.scalar(select(KeyValueSqlModel).where(KeyValueSqlModel.key == key))
        if row is None:
            session.add(KeyValueSqlModel(key=key, value=record))
        else:
            row.value = record
        await session.commit()
    except SQLAlchemyError:
        LOGGER.warning("Could not save slide photos", exc_info=True)
        await session.rollback()


async def delete_slide_photos(session: AsyncSession, presentation_id: uuid.UUID | str) -> None:
    try:
        await session.execute(
            delete(KeyValueSqlModel).where(KeyValueSqlModel.key == slide_photos_key(presentation_id))
        )
        await session.commit()
    except SQLAlchemyError:
        LOGGER.warning("Could not delete slide photos", exc_info=True)
        await session.rollback()


# --- matching ---------------------------------------------------------------

MATCH_SYSTEM_PROMPT = """
You place the user's own photos on the slides of their presentation.

You get the numbered slides (title and summary) and the photos in order
(Photo 1, Photo 2, ...). For every photo pick the slide whose content it
illustrates best, judging by what the photo actually shows.

Rules:
- Give different photos different slides whenever possible.
- Put two photos on one slide only when there are more photos than fitting slides.
- Use null when a photo fits no slide at all (for example a screenshot of a document).
- Every photo appears exactly once in the answer.
- "reason" is a few words on why, in the language of the slides.
"""


class _PhotoChoice(BaseModel):
    photo: int = Field(description="Photo number, starting at 1")
    slide: Optional[int] = Field(description="Slide number, starting at 1, or null")
    reason: str = ""


class _PhotoChoices(BaseModel):
    photos: list[_PhotoChoice]


def _slide_summary(slide: SlideOutlineModel) -> str:
    text = " ".join((slide.content or "").split())
    return text[:SLIDE_SUMMARY_CHARS]


def _photo_part(url: str) -> Optional[ImageContentPart]:
    path = resolve_image_path_to_filesystem(url)
    if not path:
        return None
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((MATCH_IMAGE_SIDE, MATCH_IMAGE_SIDE))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=82)
    except Exception:  # unreadable file: the photo is simply not shown to the model
        LOGGER.warning("Could not read photo for matching: %s", url, exc_info=True)
        return None
    return ImageContentPart(data=buffer.getvalue(), mime_type="image/jpeg")


def assign_by_order(n_photos: int, n_slides: int) -> list[Optional[int]]:
    return [index if index < n_slides else None for index in range(n_photos)]


def _clean_choices(choices: Sequence[_PhotoChoice], n_photos: int, n_slides: int) -> list[Optional[int]]:
    """Model answer (1-based) -> slide index per photo; unknown photos stay unplaced."""
    result: list[Optional[int]] = [None] * n_photos
    seen: set[int] = set()
    for choice in choices:
        photo = choice.photo - 1
        if not 0 <= photo < n_photos or photo in seen:
            continue
        seen.add(photo)
        if choice.slide is not None and 1 <= choice.slide <= n_slides:
            result[photo] = choice.slide - 1
    return result


async def match_photos_to_slides(
    photo_urls: Sequence[str], slides: Sequence[SlideOutlineModel]
) -> tuple[list[Optional[int]], str]:
    """Slide index (or None) per photo, and how it was decided."""
    if not photo_urls or not slides:
        return [None] * len(photo_urls), "order"

    parts = [_photo_part(url) for url in photo_urls]
    if not any(parts):
        return assign_by_order(len(photo_urls), len(slides)), "order"

    slide_lines = "\n".join(
        f"Slide {number}: {_slide_summary(slide)}" for number, slide in enumerate(slides, start=1)
    )
    content: list[Any] = [f"# Slides\n{slide_lines}\n\n# Photos"]
    for number, part in enumerate(parts, start=1):
        content.append(f"Photo {number}:" if part else f"Photo {number}: (could not be loaded)")
        if part:
            content.append(part)

    schema = _PhotoChoices.model_json_schema()
    try:
        answer = await asyncio.wait_for(
            generate_structured_with_schema_retries(
                get_client(config=get_llm_config()),
                get_model(),
                messages=[SystemMessage(content=MATCH_SYSTEM_PROMPT), UserMessage(content=content)],
                response_format=JSONSchemaResponse(name="photo_placement", json_schema=schema, strict=False),
                json_schema=schema,
                strict=False,
            ),
            timeout=MATCH_TIMEOUT_SECONDS,
        )
        choices = _PhotoChoices.model_validate(answer).photos
    except Exception:
        # Text-only models reject images; order still puts every photo to use.
        LOGGER.warning("Photo matching by meaning failed; placing photos in order", exc_info=True)
        return assign_by_order(len(photo_urls), len(slides)), "order"
    return _clean_choices(choices, len(photo_urls), len(slides)), "vision"


# --- layouts ----------------------------------------------------------------


def layout_image_slots(schema: Any) -> int:
    """How many image placeholders a slide layout's JSON schema has."""
    if isinstance(schema, dict):
        count = 0
        properties = schema.get("properties")
        if isinstance(properties, dict):
            count += sum(1 for key in properties if key in IMAGE_SLOT_KEYS)
        for key, value in schema.items():
            count += layout_image_slots(value)
        return count
    if isinstance(schema, list):
        return sum(layout_image_slots(item) for item in schema)
    return 0


def outline_with_photo_hints(
    outline: PresentationOutlineModel, per_slide: Sequence[Sequence[str]]
) -> PresentationOutlineModel:
    """Copy for layout selection only: slides with photos say they contain an image."""
    hinted = outline.model_copy(deep=True)
    for index, slide in enumerate(hinted.slides):
        if index < len(per_slide) and per_slide[index]:
            slide.content = f"{slide.content or ''}\n\n{PHOTO_HINT}"
    return hinted


def ensure_image_layouts(
    structure: PresentationStructureModel,
    layout: PresentationLayoutModel,
    per_slide: Sequence[Sequence[str]],
) -> list[int]:
    """Give every slide with photos a layout that can show them. Returns changed slides."""
    slots = [layout_image_slots(slide.json_schema) for slide in layout.slides]
    with_images = [index for index, count in enumerate(slots) if count > 0]
    if not with_images:
        return []
    changed: list[int] = []
    for slide_index, photos in enumerate(per_slide):
        if not photos or slide_index >= len(structure.slides):
            continue
        current = structure.slides[slide_index]
        if 0 <= current < len(slots) and slots[current] > 0:
            continue
        # Prefer a layout with as many slots as photos, then the least reused one.
        used = {index: structure.slides.count(index) for index in with_images}
        best = min(
            with_images,
            key=lambda index: (max(0, len(photos) - slots[index]), used[index], index),
        )
        structure.slides[slide_index] = best
        changed.append(slide_index)
    return changed


def align_with_inserted_slides(
    per_slide: Sequence[Sequence[str]], *, insert_at: int, inserted: int
) -> list[list[str]]:
    """Shift photo lists past slides inserted later (table of contents)."""
    aligned = [list(photos) for photos in per_slide]
    if inserted <= 0:
        return aligned
    position = min(max(insert_at, 0), len(aligned))
    return aligned[:position] + [[] for _ in range(inserted)] + aligned[position:]
