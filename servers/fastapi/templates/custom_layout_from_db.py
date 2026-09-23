import logging
import uuid
from typing import Any

import aiohttp
from fastapi import HTTPException
from sqlalchemy import select

from api.v1.auth.internal import authenticated_internal_request_headers
from models.sql.presentation_layout_code import PresentationLayoutCodeModel
from models.sql.template import TemplateModel
from services.database import async_session_maker
from templates.presentation_layout import PresentationLayoutModel
from utils.i18n import t

LOGGER = logging.getLogger(__name__)

_CUSTOM_COMPILE_URL = "http://localhost/api/template/custom"


async def load_custom_presentation_layout(layout_name: str) -> PresentationLayoutModel:
    """Load a custom template from the DB and compile layouts via Next.js (no Puppeteer)."""
    if not layout_name.startswith("custom-"):
        raise HTTPException(
            status_code=400,
            detail=t("err.customLayoutFromDb.invalidCustomTemplateId", layout_name=layout_name),
        )

    try:
        template_uuid = uuid.UUID(layout_name.replace("custom-", "", 1))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=t("err.customLayoutFromDb.invalidCustomTemplateId2"),
        ) from exc

    LOGGER.info(
        "[template_layout] loading custom template via server compile template=%r",
        layout_name,
    )

    async with async_session_maker() as session:
        template_meta = await session.get(TemplateModel, template_uuid)
        result = await session.execute(
            select(PresentationLayoutCodeModel).where(
                PresentationLayoutCodeModel.presentation == template_uuid
            )
        )
        layouts_db = result.scalars().all()

    if not template_meta:
        raise HTTPException(
            status_code=404,
            detail=t("err.customLayoutFromDb.templateNotFound", layout_name=layout_name),
        )

    if not layouts_db:
        raise HTTPException(
            status_code=404,
            detail=t("err.customLayoutFromDb.noLayoutsFoundForTemplate", layout_name=layout_name),
        )

    payload = await _compile_custom_layouts_on_nextjs(
        layout_name=layout_name,
        layouts_db=layouts_db,
    )

    slides = payload.get("slides") or []
    if not slides:
        raise HTTPException(
            status_code=404,
            detail=t("err.customLayoutFromDb.templateNotFound", layout_name=layout_name),
        )

    LOGGER.info(
        "[template_layout] custom server compile OK template=%r slides=%d",
        layout_name,
        len(slides),
    )
    return PresentationLayoutModel(**payload)


async def _compile_custom_layouts_on_nextjs(
    layout_name: str,
    layouts_db: list[PresentationLayoutCodeModel],
) -> dict[str, Any]:
    body = {
        "group": layout_name,
        "layouts": [
            {
                "layout_id": layout.layout_id,
                "layout_name": layout.layout_name,
                "layout_code": layout.layout_code,
            }
            for layout in layouts_db
        ],
    }
    headers = await authenticated_internal_request_headers()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _CUSTOM_COMPILE_URL,
                json=body,
                headers=headers,
            ) as response:
                if response.status == 200:
                    payload = await response.json()
                    if isinstance(payload, dict):
                        return payload
                    raise HTTPException(
                        status_code=500,
                        detail=t("err.customLayoutFromDb.customTemplateCompileReturnedInvalidPayload"),
                    )

                error = await response.text()
                LOGGER.error(
                    "[template_layout] custom server compile HTTP %s template=%r body=%s",
                    response.status,
                    layout_name,
                    (error or "")[:600],
                )
                if response.status == 404:
                    raise HTTPException(
                        status_code=404,
                        detail=t("err.customLayoutFromDb.templateNotFound", layout_name=layout_name),
                    )
                raise HTTPException(
                    status_code=500,
                    detail=t("err.customLayoutFromDb.failedToCompileCustomTemplateLayouts", value=error or response.status),
                )
    except HTTPException:
        raise
    except aiohttp.ClientError as exc:
        LOGGER.exception(
            "[template_layout] custom server compile request failed template=%r",
            layout_name,
        )
        raise HTTPException(
            status_code=500,
            detail=t("err.customLayoutFromDb.failedToReachTemplateCompileService", error=exc),
        ) from exc
