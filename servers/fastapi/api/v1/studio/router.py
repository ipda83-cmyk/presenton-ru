"""AI Image Studio API (signed-in users; see services/studio)."""

import asyncio
import base64
import binascii
import logging
import os
import re
import uuid
from typing import Literal, Optional
from urllib.parse import urljoin, urlparse

import aiohttp

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from models.sql.image_asset import ImageAsset
from services.database import get_async_session
from services.studio import imaging
from services.studio.arckep import StudioProviderError, StudioTimeoutError
from services.studio.models import DEFAULT_MODEL, MODELS, StudioModel, get_model
from services.studio.service import (
    STUDIO_SOURCE,
    create_images,
    edit_image,
    save_studio_image,
    studio_configured,
    studio_history,
)
from utils.asset_directory_utils import (
    filesystem_image_path_to_app_data_url,
    get_images_directory,
    resolve_image_path_to_filesystem,
)
from utils.i18n import http_error
from utils.web_search import _resolves_to_public_addresses

LOGGER = logging.getLogger(__name__)
API_V1_STUDIO_ROUTER = APIRouter(prefix="/api/v1/studio", tags=["Studio"])

MAX_INPUT_BYTES = 25 * 1024 * 1024
REMOTE_IMAGE_TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10)
REMOTE_IMAGE_MAX_REDIRECTS = 3
MAX_PROMPT_CHARS = 4000


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    model: Optional[str] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[str] = None
    quality: Optional[str] = None
    count: int = Field(default=1, ge=1, le=4)


class EditRequest(BaseModel):
    # An image of the user's (/app_data/... or an uploaded file path) or a data URL.
    image: str = Field(min_length=1)
    prompt: str = Field(default="", max_length=MAX_PROMPT_CHARS)
    model: Optional[str] = None
    # PNG data URL; transparent pixels mark the area to change.
    mask: Optional[str] = None
    reference: Optional[str] = None
    operation: Optional[Literal["upscale", "remove_bg"]] = None
    resolution: Optional[str] = None
    quality: Optional[str] = None


def asset_dict(asset: ImageAsset) -> dict:
    return {
        "id": str(asset.id),
        "created_at": asset.created_at,
        "file_url": filesystem_image_path_to_app_data_url(asset.path),
        "extras": asset.extras or {},
    }


def _model(key: Optional[str]) -> StudioModel:
    model = get_model(key)
    if model is None:
        raise http_error(400, "err.studio.unknownModel", model=key or "")
    return model


def _require_configured() -> None:
    if not studio_configured():
        raise http_error(409, "err.studio.notConfigured")


def _decode_data_url(value: str) -> bytes:
    header, _, payload = value.partition(",")
    if ";base64" not in header or not payload:
        raise http_error(400, "err.studio.invalidImage")
    if len(payload) > MAX_INPUT_BYTES * 4 // 3 + 4:
        raise http_error(413, "err.studio.imageTooLarge")
    try:
        return base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError):
        raise http_error(400, "err.studio.invalidImage")


def _app_served(path: str) -> bool:
    return path.startswith(("/app_data/", "/static/")) and ".." not in path


async def _download_public_image(url: str) -> bytes:
    """A slide picture hosted elsewhere (stock photos). Public addresses only:
    every hop is resolved and checked before it is requested (SSRF)."""
    async with aiohttp.ClientSession(timeout=REMOTE_IMAGE_TIMEOUT) as session:
        for _ in range(REMOTE_IMAGE_MAX_REDIRECTS + 1):
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise http_error(404, "err.studio.imageNotFound")
            if not await _resolves_to_public_addresses(parsed.hostname):
                raise http_error(404, "err.studio.imageNotFound")
            try:
                async with session.get(url, allow_redirects=False) as response:
                    if response.status in (301, 302, 303, 307, 308) and response.headers.get("Location"):
                        url = urljoin(url, response.headers["Location"])
                        continue
                    if response.status != 200:
                        raise http_error(404, "err.studio.imageNotFound")
                    if (response.content_length or 0) > MAX_INPUT_BYTES:
                        raise http_error(413, "err.studio.imageTooLarge")
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        data.extend(chunk)
                        if len(data) > MAX_INPUT_BYTES:
                            raise http_error(413, "err.studio.imageTooLarge")
                    return bytes(data)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                raise http_error(404, "err.studio.imageNotFound")
    raise http_error(404, "err.studio.imageNotFound")


async def load_image_input(value: str) -> bytes:
    """Bytes of a data URL, one of the user's own image files, or a public picture URL."""
    value = value.strip()
    if value.startswith("data:"):
        data = _decode_data_url(value)
    elif value.lower().startswith(("http://", "https://")) and not _app_served(urlparse(value).path):
        data = await _download_public_image(value)
    else:
        # Only app-served pictures (the user's own, or bundled ones), never other server files.
        path = resolve_image_path_to_filesystem(value) if _app_served(urlparse(value).path) else None
        if not path:
            raise http_error(404, "err.studio.imageNotFound")
        if os.path.getsize(path) > MAX_INPUT_BYTES:
            raise http_error(413, "err.studio.imageTooLarge")
        with open(path, "rb") as file:
            data = file.read()
    if not data:
        raise http_error(400, "err.studio.invalidImage")
    try:
        imaging.open_image(data)
    except imaging.InvalidImageError:
        raise http_error(400, "err.studio.invalidImage")
    return data


def _provider_error(error: StudioProviderError):
    LOGGER.warning("Studio provider error: status=%s code=%s detail=%s", error.status, error.code, error.detail)
    if isinstance(error, StudioTimeoutError):
        return http_error(504, "err.studio.timeout")
    if error.status == 402 or (error.code or "").upper() == "INSUFFICIENT_BALANCE":
        return http_error(402, "err.studio.insufficientBalance")
    if error.status in (401, 403):
        # e.g. "API key is missing required scope 'images:write'"
        scope = re.search(r"scope '([\w:.-]+)'", error.detail or "")
        if scope:
            return http_error(502, "err.studio.keyScope", scope=scope.group(1))
        return http_error(502, "err.studio.providerAuth")
    if error.status == 429:
        return http_error(429, "err.studio.rateLimited")
    return http_error(502, "err.studio.providerFailed", detail=error.detail)


@API_V1_STUDIO_ROUTER.get("/config")
async def studio_config():
    return {
        "configured": studio_configured(),
        "default_model": DEFAULT_MODEL,
        "models": [model.public() for model in MODELS.values()],
    }


@API_V1_STUDIO_ROUTER.post("/generate")
async def studio_generate(
    body: GenerateRequest, session: AsyncSession = Depends(get_async_session)
):
    model = _model(body.model)
    _require_configured()
    try:
        images = await create_images(
            model,
            body.prompt,
            aspect_ratio=body.aspect_ratio,
            resolution=body.resolution,
            quality=body.quality,
            count=body.count,
        )
    except StudioProviderError as error:
        raise _provider_error(error)
    except imaging.InvalidImageError:
        raise http_error(502, "err.studio.providerFailed", detail="invalid image")
    extras = {
        "mode": "create",
        "prompt": body.prompt.strip(),
        "model": model.key,
        "aspect_ratio": body.aspect_ratio,
        "resolution": body.resolution,
    }
    assets = [await save_studio_image(session, image, extras) for image in images]
    return {"images": [asset_dict(asset) for asset in assets]}


@API_V1_STUDIO_ROUTER.post("/edit")
async def studio_edit(body: EditRequest, session: AsyncSession = Depends(get_async_session)):
    model = _model(body.model)
    # Operations and reference inserts carry their own instructions.
    if not body.operation and not body.reference and not body.prompt.strip():
        raise http_error(400, "err.studio.promptRequired")
    source = await load_image_input(body.image)
    mask = await load_image_input(body.mask) if body.mask else None
    reference = await load_image_input(body.reference) if body.reference else None
    _require_configured()
    try:
        result = await edit_image(
            model,
            source,
            body.prompt,
            mask=mask,
            reference=reference,
            operation=body.operation,
            resolution=body.resolution,
            quality=body.quality,
        )
    except StudioProviderError as error:
        raise _provider_error(error)
    except imaging.InvalidImageError:
        raise http_error(502, "err.studio.providerFailed", detail="invalid image")
    mode = body.operation or ("reference" if reference else "brush" if mask else "edit")
    asset = await save_studio_image(
        session,
        result,
        {
            "mode": mode,
            "prompt": body.prompt.strip(),
            "model": model.key,
            "parent": body.image if not body.image.startswith("data:") else None,
        },
    )
    return {"image": asset_dict(asset)}


@API_V1_STUDIO_ROUTER.get("/history")
async def studio_history_list(
    limit: int = Query(default=60, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
):
    return {"images": [asset_dict(asset) for asset in await studio_history(session, limit)]}


@API_V1_STUDIO_ROUTER.delete("/history/{asset_id}", status_code=204)
async def studio_history_delete(
    asset_id: uuid.UUID, session: AsyncSession = Depends(get_async_session)
):
    asset = await session.get(ImageAsset, asset_id)
    if asset is None or (asset.extras or {}).get("source") != STUDIO_SOURCE:
        raise http_error(404, "err.studio.imageNotFound")
    path = asset.path
    await session.delete(asset)
    await session.commit()
    images_root = os.path.realpath(get_images_directory())
    try:
        real = os.path.realpath(path)
        if os.path.commonpath([real, images_root]) == images_root and os.path.isfile(real):
            os.remove(real)
    except (OSError, ValueError):
        LOGGER.warning("Could not remove Studio image file", exc_info=True)
    return Response(status_code=204)
