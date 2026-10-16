import asyncio
import json
import logging
import traceback
import uuid
from typing import List, Literal, Optional

import dirtyjson
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from constants.presentation import MAX_NUMBER_OF_SLIDES
from models.presentation_outline_model import PresentationOutlineModel, SlideOutlineModel
from models.sql.presentation import PresentationModel
from models.sse_response import (
    SSECompleteResponse,
    SSEErrorResponse,
    SSEResponse,
    SSEStatusResponse,
)
from services.temp_file_service import TEMP_FILE_SERVICE
from services.database import get_async_session
from services.documents_loader import DocumentsLoader
from services.mem0_presentation_memory_service import (
    MEM0_PRESENTATION_MEMORY_SERVICE,
)
from utils.llm_utils import loads_model_json, message_content_to_text
from utils.outline_utils import (
    get_no_of_outlines_to_generate_for_n_slides,
    get_presentation_title_from_presentation_outline,
)
from utils.outline_limits import normalize_outline_payload
from utils.llm_calls.generate_presentation_outlines import (
    OutlineGenerationStatus,
    OutlineWebSources,
    generate_ppt_outline,
    get_messages as get_outline_messages,
)
from utils.sse import safe_sse_stream
from utils.web_search import get_selected_web_search_provider, get_web_search_route
from utils.web_sources import (
    build_web_sources_record,
    get_web_sources,
    save_web_sources,
)
from utils.slide_photos import (
    MAX_PHOTOS,
    build_record as build_slide_photos_record,
    get_slide_photos,
    match_photos_to_slides,
    normalize_photos,
    save_slide_photos,
)
from utils.i18n import t

OUTLINES_ROUTER = APIRouter(prefix="/outlines", tags=["Outlines"])
LOGGER = logging.getLogger(__name__)


@OUTLINES_ROUTER.get("/{id}", response_model=PresentationOutlineModel)
async def get_outline(
    id: uuid.UUID,
    sql_session: AsyncSession = Depends(get_async_session),
):
    presentation = await sql_session.get(PresentationModel, id)
    if not presentation:
        raise HTTPException(status_code=404, detail=t("err.outlines.presentationNotFound"))

    if not presentation.outlines:
        return PresentationOutlineModel(slides=[])

    return PresentationOutlineModel(**presentation.outlines)


@OUTLINES_ROUTER.put("/{id}", response_model=PresentationOutlineModel)
async def update_outline(
    id: uuid.UUID,
    outline: PresentationOutlineModel,
    sql_session: AsyncSession = Depends(get_async_session),
):
    presentation = await sql_session.get(PresentationModel, id)
    if not presentation:
        raise HTTPException(status_code=404, detail=t("err.outlines.presentationNotFound"))

    presentation.outlines = outline.model_dump(mode="json")
    presentation.n_slides = len(outline.slides)
    presentation.title = get_presentation_title_from_presentation_outline(outline)

    sql_session.add(presentation)
    await sql_session.commit()

    await MEM0_PRESENTATION_MEMORY_SERVICE.store_generated_outlines(
        presentation.id,
        presentation.outlines,
    )

    return outline


@OUTLINES_ROUTER.get("/{id}/sources")
async def get_outline_web_sources(
    id: uuid.UUID,
    sql_session: AsyncSession = Depends(get_async_session),
):
    """Web pages the outline was researched from (see utils/web_sources.py)."""
    presentation = await sql_session.get(PresentationModel, id)
    if not presentation:
        raise HTTPException(status_code=404, detail=t("err.outlines.presentationNotFound"))
    record = await get_web_sources(sql_session, id)
    # "none": the outline was made before sources were recorded.
    return record or build_web_sources_record(status="none")


class SlidePhotoIn(BaseModel):
    url: str = Field(min_length=1, max_length=1024)
    name: Optional[str] = Field(default=None, max_length=255)
    slide: Optional[int] = Field(default=None, ge=0)


class SlidePhotosUpdate(BaseModel):
    photos: List[SlidePhotoIn] = Field(max_length=MAX_PHOTOS)
    matched: Optional[Literal["vision", "order", "manual"]] = None


class SlidePhotosMatchRequest(BaseModel):
    # The outline as shown (it may have unsaved edits); stored outline otherwise.
    slides: Optional[List[SlideOutlineModel]] = Field(default=None, max_length=MAX_NUMBER_OF_SLIDES)


async def _presentation_or_404(sql_session: AsyncSession, id: uuid.UUID) -> PresentationModel:
    presentation = await sql_session.get(PresentationModel, id)
    if not presentation:
        raise HTTPException(status_code=404, detail=t("err.outlines.presentationNotFound"))
    return presentation


@OUTLINES_ROUTER.get("/{id}/photos")
async def get_outline_photos(
    id: uuid.UUID,
    sql_session: AsyncSession = Depends(get_async_session),
):
    """The user's photos and the slides they go on (see utils/slide_photos.py)."""
    await _presentation_or_404(sql_session, id)
    record = await get_slide_photos(sql_session, id)
    return record or build_slide_photos_record([], None)


@OUTLINES_ROUTER.put("/{id}/photos")
async def put_outline_photos(
    id: uuid.UUID,
    body: SlidePhotosUpdate,
    sql_session: AsyncSession = Depends(get_async_session),
):
    await _presentation_or_404(sql_session, id)
    photos = normalize_photos(photo.model_dump() for photo in body.photos)
    record = build_slide_photos_record(photos, body.matched)
    await save_slide_photos(sql_session, id, record)
    return record


@OUTLINES_ROUTER.post("/{id}/photos/match")
async def match_outline_photos(
    id: uuid.UUID,
    body: SlidePhotosMatchRequest,
    sql_session: AsyncSession = Depends(get_async_session),
):
    """Place every photo on the slide it illustrates best (vision model, else in order)."""
    presentation = await _presentation_or_404(sql_session, id)
    record = await get_slide_photos(sql_session, id)
    photos = normalize_photos((record or {}).get("photos") or [])
    if not photos:
        return build_slide_photos_record([], None)
    slides = body.slides
    if slides is None:
        slides = PresentationOutlineModel(**(presentation.outlines or {"slides": []})).slides
    # Release the read transaction while the model looks at the photos.
    await sql_session.commit()
    assignment, method = await match_photos_to_slides([photo["url"] for photo in photos], slides)
    for photo, slide in zip(photos, assignment):
        photo["slide"] = slide
    record = build_slide_photos_record(photos, method)
    await save_slide_photos(sql_session, id, record)
    return record


@OUTLINES_ROUTER.get("/stream/{id}")
async def stream_outlines(
    id: uuid.UUID,
    request: Request,
    sql_session: AsyncSession = Depends(get_async_session),
):
    presentation = await sql_session.get(PresentationModel, id)

    if not presentation:
        raise HTTPException(status_code=404, detail=t("err.outlines.presentationNotFound"))

    search_route, actual_search_provider = get_web_search_route()
    LOGGER.info(
        "Starting outline stream: presentation_id=%s web_search_enabled=%s "
        "selected_web_search_provider=%s web_search_route=%s actual_web_search_provider=%s",
        presentation.id,
        presentation.web_search,
        get_selected_web_search_provider().value,
        search_route,
        (
            actual_search_provider.value
            if actual_search_provider
            else ("model-native" if search_route == "native" else "none")
        ),
    )

    temp_dir = TEMP_FILE_SERVICE.create_temp_dir()

    async def inner():
        if await request.is_disconnected():
            return

        yield SSEStatusResponse(
            status=t("stream.outlinePreparing")
        ).to_string()

        additional_context = ""
        if presentation.file_paths:
            documents_loader = DocumentsLoader(
                file_paths=presentation.file_paths,
                presentation_language=presentation.language,
            )
            await documents_loader.load_documents(temp_dir)
            documents = documents_loader.documents
            if documents:
                additional_context = "\n\n".join(documents)

        presentation_outlines_text = ""

        if presentation.n_slides > 0:
            n_slides_to_generate = get_no_of_outlines_to_generate_for_n_slides(
                n_slides=presentation.n_slides,
                toc=presentation.include_table_of_contents,
                title_slide=presentation.include_title_slide,
            )
        else:
            n_slides_to_generate = None

        outline_messages = get_outline_messages(
            presentation.content,
            n_slides_to_generate,
            presentation.language,
            additional_context,
            presentation.tone,
            presentation.verbosity,
            presentation.instructions,
            presentation.include_title_slide,
            presentation.include_table_of_contents,
        )
        await MEM0_PRESENTATION_MEMORY_SERVICE.store_generation_context(
            presentation_id=presentation.id,
            system_prompt=(
                message_content_to_text(outline_messages[0].content)
                if len(outline_messages) > 0
                else None
            ),
            user_prompt=(
                message_content_to_text(outline_messages[1].content)
                if len(outline_messages) > 1
                else None
            ),
            extracted_document_text=additional_context,
            source_content=presentation.content,
            instructions=presentation.instructions,
        )

        async for chunk in generate_ppt_outline(
            presentation.content,
            n_slides_to_generate,
            presentation.language,
            additional_context,
            presentation.tone,
            presentation.verbosity,
            presentation.instructions,
            presentation.include_title_slide,
            presentation.web_search,
            presentation.include_table_of_contents,
            emit_statuses=True,
            disconnect_checker=request.is_disconnected,
        ):
            # Give control to the event loop
            await asyncio.sleep(0)

            if isinstance(chunk, OutlineGenerationStatus):
                LOGGER.info(
                    "Outline generation status: presentation_id=%s status=%s",
                    presentation.id,
                    chunk.message,
                )
                yield SSEStatusResponse(status=chunk.message).to_string()
                continue

            if isinstance(chunk, OutlineWebSources):
                record = build_web_sources_record(
                    status=chunk.status,
                    provider=chunk.provider,
                    query=chunk.query,
                    results=chunk.results,
                )
                LOGGER.info(
                    "Outline web sources: presentation_id=%s status=%s provider=%s sources=%d",
                    presentation.id,
                    record["status"],
                    record["provider"],
                    len(record["sources"]),
                )
                await save_web_sources(sql_session, presentation.id, record)
                yield SSEResponse(
                    event="response",
                    data=json.dumps({"type": "sources", **record}),
                ).to_string()
                continue

            if isinstance(chunk, HTTPException):
                yield SSEErrorResponse(detail=chunk.detail).to_string()
                return

            yield SSEResponse(
                event="response",
                data=json.dumps({"type": "chunk", "chunk": chunk}),
            ).to_string()

            presentation_outlines_text += chunk

        try:
            presentation_outlines_json = dict(
                loads_model_json(presentation_outlines_text)
            )
        except Exception as e:
            traceback.print_exc()
            LOGGER.warning(
                "Outline answer is not JSON (start: %r)", presentation_outlines_text[:300]
            )
            yield SSEErrorResponse(
                detail=(
                    t("err.presentation.failedToGeneratePresentationOutlinesPlease")
                    + f" {e}"
                ),
            ).to_string()
            return

        presentation_outlines = PresentationOutlineModel(
            **normalize_outline_payload(
                presentation_outlines_json,
                MAX_NUMBER_OF_SLIDES,
            )
        )

        # Only undershooting is fatal. Overshooting is trimmed just below --
        # the slice was already here, unreachable for that case because this
        # check rejected the request first.
        if (
            n_slides_to_generate is not None
            and len(presentation_outlines.slides) < n_slides_to_generate
        ):
            yield SSEErrorResponse(
                detail=t("err.presentation.failedToGeneratePresentationOutlinesWith")
            ).to_string()
            return

        if n_slides_to_generate is not None:
            presentation_outlines.slides = presentation_outlines.slides[
                :n_slides_to_generate
            ]

        if presentation.n_slides <= 0:
            presentation.n_slides = len(presentation_outlines.slides)

        presentation.outlines = presentation_outlines.model_dump()
        presentation.title = get_presentation_title_from_presentation_outline(
            presentation_outlines
        )

        sql_session.add(presentation)
        await sql_session.commit()

        await MEM0_PRESENTATION_MEMORY_SERVICE.store_generated_outlines(
            presentation.id,
            presentation.outlines,
        )

        yield SSECompleteResponse(
            key="presentation", value=presentation.model_dump(mode="json")
        ).to_string()

    async def rollback_stream_session():
        await sql_session.rollback()

    return StreamingResponse(
        safe_sse_stream(
            inner(),
            logger=LOGGER,
            error_detail="Failed to generate presentation outlines. Please try again.",
            on_error=rollback_stream_session,
        ),
        media_type="text/event-stream",
    )
