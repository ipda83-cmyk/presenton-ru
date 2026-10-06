import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from api.v1.ppt.endpoints import outlines as outlines_endpoint
from tests.conftest import FakeAsyncSession
from utils.llm_calls.generate_presentation_outlines import OutlineWebSources
from utils.web_search import WebSearchResult


class _Request:
    async def is_disconnected(self):
        return False


def _presentation():
    return SimpleNamespace(
        id=uuid.uuid4(),
        web_search=True,
        file_paths=None,
        n_slides=1,
        include_table_of_contents=False,
        include_title_slide=False,
        content="Taipei zoo",
        language="Auto (Russian)",
        tone="default",
        verbosity="standard",
        instructions=None,
        outlines=None,
        title=None,
        model_dump=lambda mode=None: {"id": "p"},
    )


def _events(body: str) -> list[dict]:
    events = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[len("data: "):]))
                except json.JSONDecodeError:
                    pass
    return events


def _run_stream(generated_chunks):
    presentation = _presentation()
    session = FakeAsyncSession({presentation.id: presentation})
    saved = []

    async def fake_generate(*_args, **_kwargs):
        for chunk in generated_chunks:
            yield chunk

    async def fake_save(_session, presentation_id, record):
        saved.append((presentation_id, record))

    async def collect():
        response = await outlines_endpoint.stream_outlines(
            presentation.id, _Request(), session
        )
        parts = []
        async for part in response.body_iterator:
            parts.append(part if isinstance(part, str) else part.decode())
        return "".join(parts)

    with patch.object(outlines_endpoint, "generate_ppt_outline", fake_generate), patch.object(
        outlines_endpoint, "save_web_sources", fake_save
    ), patch.object(
        outlines_endpoint, "get_outline_messages", return_value=[]
    ), patch.object(
        outlines_endpoint.MEM0_PRESENTATION_MEMORY_SERVICE,
        "store_generation_context",
        AsyncMock(),
    ), patch.object(
        outlines_endpoint.MEM0_PRESENTATION_MEMORY_SERVICE,
        "store_generated_outlines",
        AsyncMock(),
    ):
        body = asyncio.run(collect())
    return presentation, _events(body), saved


def test_outline_stream_reports_and_saves_web_sources():
    presentation, events, saved = _run_stream(
        [
            OutlineWebSources(
                status="ok",
                provider="perplexity",
                query="taipei zoo",
                results=(
                    WebSearchResult("Taipei Zoo", "https://www.zoo.gov.taipei/", "Largest zoo."),
                    WebSearchResult("Bad", "javascript:alert(1)", "x"),
                ),
            ),
            '{"slides": [{"content": "## Taipei Zoo"}]}',
        ]
    )

    sources_events = [event for event in events if event.get("type") == "sources"]
    assert len(sources_events) == 1
    event = sources_events[0]
    assert event["status"] == "ok"
    assert event["provider"] == "perplexity"
    assert [source["url"] for source in event["sources"]] == ["https://www.zoo.gov.taipei/"]
    assert event["sources"][0]["domain"] == "zoo.gov.taipei"

    assert len(saved) == 1
    assert saved[0][0] == presentation.id
    assert saved[0][1]["sources"] == event["sources"]
    # The outline itself still streams and completes after the sources.
    assert any(event.get("type") == "chunk" for event in events)
    assert any(event.get("type") == "complete" for event in events)


def test_outline_stream_reports_why_there_are_no_sources():
    _, events, saved = _run_stream(
        [
            OutlineWebSources(status="native", provider="model-native"),
            '{"slides": [{"content": "## Taipei Zoo"}]}',
        ]
    )

    sources_events = [event for event in events if event.get("type") == "sources"]
    assert [event["status"] for event in sources_events] == ["native"]
    assert sources_events[0]["sources"] == []
    assert saved[0][1]["status"] == "native"
