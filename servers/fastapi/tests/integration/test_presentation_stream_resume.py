"""A flaky model must not send the deck back to slide 1 on every reconnect."""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException

from api.v1.ppt.endpoints import presentation as presentation_endpoint
from models.sql.presentation import PresentationModel, PresentationVersion
from models.sql.slide import SlideModel
from tests.conftest import FakeAsyncSession
from utils import slide_generation_resume

LAYOUT = {
    "id": "template-layout-1",
    "description": "Hero layout",
    "components": [
        {
            "id": "hero",
            "description": "Hero content",
            "elements": [{"type": "text", "decorative": False, "name": "headline", "min_length": 1, "max_length": 32}],
        }
    ],
}


def _presentation(presentation_id):
    now = datetime.now()
    return PresentationModel(
        id=presentation_id,
        version=PresentationVersion.V2_STANDARD,
        content="deck",
        n_slides=3,
        language="English",
        title="Deck",
        outlines={"slides": [{"content": "## One"}, {"content": "## Two"}, {"content": "## Three"}]},
        layout={"layouts": [LAYOUT]},
        structure={"slides": [0, 0, 0]},
        tone="default",
        verbosity="standard",
        instructions=None,
        created_at=now,
        updated_at=now,
    )


def test_stream_retries_a_flaky_slide_and_resumes_after_reconnect(monkeypatch):
    monkeypatch.setattr(slide_generation_resume, "RETRY_DELAYS_SECONDS", (0.0, 0.0))
    presentation_id = uuid.uuid4()
    presentation = _presentation(presentation_id)
    calls: list[int] = []
    slide_3_down = {"value": True}

    async def flaky_slide_content(_slide_layout, *_args, **kwargs):
        number = kwargs["slide_number"]
        calls.append(number)
        if number == 3 and slide_3_down["value"]:
            raise HTTPException(status_code=504, detail="Request timed out")
        return {"hero": {"headline": f"Slide {number}"}, "__speaker_note__": "Note for the slide."}

    async def consume(session):
        response = await presentation_endpoint.stream_presentation(id=presentation_id, sql_session=session)
        return "".join([chunk async for chunk in response.body_iterator])

    with patch.object(
        presentation_endpoint, "get_slide_content_from_type_and_outline", new=flaky_slide_content
    ), patch.object(
        presentation_endpoint, "process_slide_and_fetch_assets", new=AsyncMock(return_value=[])
    ), patch.object(presentation_endpoint, "get_images_directory", return_value="/tmp"), patch.object(
        presentation_endpoint, "ImageGenerationService", return_value=Mock()
    ):
        first_session = FakeAsyncSession(get_results={presentation_id: presentation})
        first = asyncio.run(consume(first_session))
        assert "Request timed out" in first
        assert calls == [1, 2, 3, 3, 3]  # slide 3 tried three times before giving up
        assert not [item for item in first_session.added_all if isinstance(item, SlideModel)]

        # The browser reconnects once the model is back.
        slide_3_down["value"] = False
        calls.clear()
        second_session = FakeAsyncSession(get_results={presentation_id: presentation})
        asyncio.run(consume(second_session))
        assert calls == [3]  # slides 1 and 2 are replayed, not written again
        saved = [item for item in second_session.added_all if isinstance(item, SlideModel)]
        assert [slide.content["hero"]["headline"] for slide in saved] == ["Slide 1", "Slide 2", "Slide 3"]

        # Finished: regenerating later writes every slide anew.
        calls.clear()
        asyncio.run(consume(FakeAsyncSession(get_results={presentation_id: presentation})))
        assert calls == [1, 2, 3]


def test_stream_retries_an_empty_answer_without_failing(monkeypatch):
    monkeypatch.setattr(slide_generation_resume, "RETRY_DELAYS_SECONDS", (0.0, 0.0))
    presentation_id = uuid.uuid4()
    presentation = _presentation(presentation_id)
    attempts = {"slide 2": 0}

    async def sometimes_empty(_slide_layout, *_args, **kwargs):
        number = kwargs["slide_number"]
        if number == 2 and attempts["slide 2"] == 0:
            attempts["slide 2"] += 1
            raise HTTPException(status_code=400, detail=presentation_endpoint.t("err.llmUtils.llmDidNotReturnAnyContent"))
        return {"hero": {"headline": f"Slide {number}"}, "__speaker_note__": "Note for the slide."}

    async def consume(session):
        response = await presentation_endpoint.stream_presentation(id=presentation_id, sql_session=session)
        return "".join([chunk async for chunk in response.body_iterator])

    with patch.object(
        presentation_endpoint, "get_slide_content_from_type_and_outline", new=sometimes_empty
    ), patch.object(
        presentation_endpoint, "process_slide_and_fetch_assets", new=AsyncMock(return_value=[])
    ), patch.object(presentation_endpoint, "get_images_directory", return_value="/tmp"), patch.object(
        presentation_endpoint, "ImageGenerationService", return_value=Mock()
    ):
        session = FakeAsyncSession(get_results={presentation_id: presentation})
        body = asyncio.run(consume(session))
    assert '"type": "error"' not in body
    assert len([item for item in session.added_all if isinstance(item, SlideModel)]) == 3
