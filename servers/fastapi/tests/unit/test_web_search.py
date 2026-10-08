import asyncio
import logging

from enums.llm_provider import LLMProvider
from enums.web_search_provider import WebSearchProvider
from utils import web_search


def test_auto_uses_native_search_for_supported_llm(monkeypatch):
    monkeypatch.setenv("LLM", LLMProvider.OPENAI.value)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.AUTO.value)

    assert web_search.should_use_native_web_search() is True
    assert web_search.should_expose_external_web_search_tool() is False


def test_auto_reports_unavailable_without_configured_external_provider(monkeypatch):
    monkeypatch.setenv("LLM", LLMProvider.OLLAMA.value)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.AUTO.value)

    assert web_search.should_use_native_web_search() is False
    assert web_search.should_expose_external_web_search_tool() is False


def test_auto_still_hides_external_search_when_configured(monkeypatch):
    monkeypatch.setenv("LLM", LLMProvider.OLLAMA.value)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.AUTO.value)

    assert web_search.should_use_native_web_search() is False
    assert web_search.should_expose_external_web_search_tool() is False


def test_get_web_search_route_reports_unavailable_without_configured_external_provider(monkeypatch):
    monkeypatch.setenv("LLM", LLMProvider.OLLAMA.value)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.AUTO.value)

    assert web_search.get_web_search_route() == ("unavailable", None)


def test_explicit_external_search_overrides_native_llm(monkeypatch):
    monkeypatch.setenv("LLM", LLMProvider.OPENAI.value)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.TAVILY.value)

    assert web_search.should_use_native_web_search() is False
    assert web_search.should_expose_external_web_search_tool() is True


def test_explicit_brave_search_is_supported(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.BRAVE.value)

    assert web_search.resolve_external_web_search_provider() == WebSearchProvider.BRAVE
    assert web_search.should_expose_external_web_search_tool() is True


def test_explicit_serper_search_is_supported(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.SERPER.value)

    assert web_search.resolve_external_web_search_provider() == WebSearchProvider.SERPER
    assert web_search.should_expose_external_web_search_tool() is True


def test_explicit_exa_search_is_supported(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.EXA.value)

    assert web_search.resolve_external_web_search_provider() == WebSearchProvider.EXA
    assert web_search.should_expose_external_web_search_tool() is True


def test_explicit_native_search_does_not_fallback_for_unsupported_llm(monkeypatch):
    monkeypatch.setenv("LLM", LLMProvider.OLLAMA.value)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.NATIVE.value)

    assert web_search.should_use_native_web_search() is False
    assert web_search.should_expose_external_web_search_tool() is False


def test_auto_does_not_expose_external_search_when_native_tools_are_unavailable(monkeypatch):
    monkeypatch.setenv("LLM", LLMProvider.GOOGLE.value)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.AUTO.value)

    assert web_search.should_use_native_web_search() is True
    assert (
        web_search.should_expose_external_web_search_tool(
            native_search_available=False
        )
        is False
    )


def test_format_web_search_context_excludes_source_urls():
    context = web_search.format_web_search_context(
        [
            web_search.WebSearchResult(
                title="Presenton",
                url="https://example.com/presenton",
                snippet=(
                    "Presentation generation [6][7] with "
                    "[documentation](https://example.com/docs)"
                ),
            )
        ]
    )

    assert "Web search results" in context
    assert "https://example.com/presenton" not in context
    assert "https://example.com/docs" not in context
    assert "URL:" not in context
    assert "[6]" not in context
    assert "documentation" in context
    assert "Presentation generation" in context


def test_auto_does_not_resolve_external_provider_from_configuration(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.AUTO.value)
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("TAVILY_API_KEY", "configured-tavily-key")

    assert web_search.resolve_external_web_search_provider() is None


def test_explicit_external_provider_is_not_replaced(monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.SEARXNG.value)
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")

    assert (
        web_search.resolve_external_web_search_provider()
        == WebSearchProvider.SEARXNG
    )


def test_web_search_route_reports_actual_external_provider(monkeypatch):
    monkeypatch.setenv("LLM", LLMProvider.OPENAI.value)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.SEARXNG.value)
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")

    assert web_search.get_web_search_route() == (
        "external",
        WebSearchProvider.SEARXNG,
    )


def test_web_search_route_reports_model_native(monkeypatch):
    monkeypatch.setenv("LLM", LLMProvider.OPENAI.value)
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.AUTO.value)

    assert web_search.get_web_search_route() == ("native", None)


def test_searxng_accepts_base_or_search_url(monkeypatch):
    monkeypatch.setenv("SEARXNG_BASE_URL", "http://127.0.0.1:8080")
    assert web_search._get_searxng_search_url() == "http://127.0.0.1:8080/search"

    monkeypatch.setenv(
        "SEARXNG_BASE_URL",
        "http://127.0.0.1:8080/search?q=ignored&format=json",
    )
    assert web_search._get_searxng_search_url() == "http://127.0.0.1:8080/search"


def test_searxng_log_url_redacts_credentials():
    assert (
        web_search._redact_url_credentials("http://user:secret@127.0.0.1:8080/search")
        == "http://***:***@127.0.0.1:8080/search"
    )


def test_search_web_logs_provider_and_clamps_max_results(monkeypatch, caplog):
    captured = {}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    async def fake_search(_session, query, limit):
        captured.update(query=query, limit=limit)
        return [
            web_search.WebSearchResult(
                title="Presenton",
                url="https://example.com/presenton",
            )
    ]

    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.SEARXNG.value)
    monkeypatch.setattr(
        web_search.aiohttp,
        "ClientSession",
        lambda **_kwargs: FakeSession(),
    )
    monkeypatch.setattr(web_search, "_search_searxng", fake_search)
    caplog.set_level(logging.INFO, logger=web_search.__name__)

    results = asyncio.run(web_search.search_web(" current facts ", max_results=50))

    assert captured == {"query": "current facts", "limit": 10}
    assert len(results) == 1
    assert "provider=searxng" in caplog.text
    assert "results=1" in caplog.text


def test_exa_search_requests_highlights_and_maps_results(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def json(self, content_type=None):
            return {
                "results": [
                    {
                        "title": "Presenton",
                        "url": "https://example.com/presenton",
                        "highlights": ["AI presentations.", "Open source."],
                    },
                    {
                        "title": "Fallback",
                        "url": "https://example.com/fallback",
                        "highlights": [],
                        "summary": "Summary fallback.",
                    },
                ]
            }

    class FakeSession:
        def post(self, url, json, headers):
            captured.update(url=url, json=json, headers=headers)
            return FakeResponse()

    monkeypatch.setenv("EXA_API_KEY", "test-exa-key")

    results = asyncio.run(
        web_search._search_exa(FakeSession(), "presentation ai", 2)
    )

    assert captured == {
        "url": "https://api.exa.ai/search",
        "json": {
            "query": "presentation ai",
            "numResults": 2,
            "contents": {"highlights": True},
        },
        "headers": {"x-api-key": "test-exa-key"},
    }
    assert results == [
        web_search.WebSearchResult(
            title="Presenton",
            url="https://example.com/presenton",
            snippet="AI presentations. Open source.",
        ),
        web_search.WebSearchResult(
            title="Fallback",
            url="https://example.com/fallback",
            snippet="Summary fallback.",
        ),
    ]


def test_default_search_is_gemini_then_perplexity_by_configured_key(monkeypatch):
    monkeypatch.delenv("WEB_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.AUTO

    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-perplexity-key")
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.PERPLEXITY
    assert web_search.get_web_search_route() == ("external", WebSearchProvider.PERPLEXITY)

    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.GEMINI
    assert web_search.get_web_search_route() == ("external", WebSearchProvider.GEMINI)

    # An empty setting (cleared in the UI) also falls back to the default.
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "  ")
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.GEMINI


def test_explicit_provider_wins_over_the_default(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-perplexity-key")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.PERPLEXITY.value)
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.PERPLEXITY

    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.AUTO.value)
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.AUTO


def _fake_gemini_response(chunks, supports, text="Answer text."):
    from types import SimpleNamespace as NS

    return NS(
        text=text,
        candidates=[
            NS(
                grounding_metadata=NS(
                    grounding_chunks=[
                        NS(web=NS(uri=uri, title=title, domain=domain))
                        for uri, title, domain in chunks
                    ],
                    grounding_supports=[
                        NS(segment=NS(text=segment), grounding_chunk_indices=indices)
                        for segment, indices in supports
                    ],
                )
            )
        ],
    )


def test_gemini_search_uses_google_search_grounding_and_maps_sources(monkeypatch):
    captured = {}
    response = _fake_gemini_response(
        chunks=[
            ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/a", "zoo.gov.taipei", "zoo.gov.taipei"),
            ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/b", "wikipedia.org", None),
            ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/a", "dup", "dup"),
            ("https://vertexaisearch.cloud.google.com/grounding-api-redirect/c", "unused.org", "unused.org"),
        ],
        supports=[
            ("Taipei Zoo opened in 1914.", [0]),
            ("It covers 165 hectares.", [0, 1]),
        ],
    )

    class FakeModels:
        async def generate_content(self, model, contents, config):
            captured.update(model=model, contents=contents, config=config)
            return response

    class FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.aio = type("Aio", (), {"models": FakeModels()})()

    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.delenv("GEMINI_SEARCH_MODEL", raising=False)
    monkeypatch.setattr(web_search, "_gemini_client", FakeClient)

    results = asyncio.run(web_search._search_gemini("taipei zoo", 2))

    assert captured["api_key"] == "test-google-key"
    assert captured["model"] == web_search.DEFAULT_GEMINI_SEARCH_MODEL
    assert "taipei zoo" in captured["contents"]
    assert captured["config"].tools[0].google_search is not None
    assert results == [
        web_search.WebSearchResult(
            title="zoo.gov.taipei",
            url="https://vertexaisearch.cloud.google.com/grounding-api-redirect/a",
            snippet="Taipei Zoo opened in 1914. It covers 165 hectares.",
            domain="zoo.gov.taipei",
        ),
        web_search.WebSearchResult(
            title="wikipedia.org",
            url="https://vertexaisearch.cloud.google.com/grounding-api-redirect/b",
            snippet="It covers 165 hectares.",
            domain="wikipedia.org",
        ),
    ]


def test_gemini_search_model_can_be_overridden_and_needs_a_key(monkeypatch):
    captured = {}

    class FakeModels:
        async def generate_content(self, model, contents, config):
            captured["model"] = model
            return _fake_gemini_response(chunks=[], supports=[])

    class FakeClient:
        def __init__(self, api_key):
            self.aio = type("Aio", (), {"models": FakeModels()})()

    monkeypatch.setattr(web_search, "_gemini_client", FakeClient)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("GEMINI_SEARCH_MODEL", "gemini-3.5-flash-lite")
    assert asyncio.run(web_search._search_gemini("q", 3)) == []
    assert captured["model"] == "gemini-3.5-flash-lite"

    monkeypatch.delenv("GOOGLE_API_KEY")
    try:
        asyncio.run(web_search._search_gemini("q", 3))
    except web_search.HTTPException as error:
        assert error.status_code == 400
        assert "GOOGLE_API_KEY" in error.detail
    else:  # pragma: no cover
        raise AssertionError("missing key was accepted")


def test_perplexity_search_requests_search_api_and_maps_results(monkeypatch):
    captured = {}
    long_snippet = "x" * 5000

    class FakeResponse:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def json(self, content_type=None):
            return {
                "results": [
                    {
                        "title": "Taipei Zoo",
                        "url": "https://www.zoo.gov.taipei/",
                        "snippet": "Taipei Zoo is the largest zoo in Taiwan.",
                        "date": "2026-01-01",
                    },
                    {"title": "No URL", "snippet": "dropped"},
                    "not an object",
                    {"title": "Long", "url": "https://example.com/long", "snippet": long_snippet},
                ]
            }

    class FakeSession:
        def post(self, url, json, headers):
            captured.update(url=url, json=json, headers=headers)
            return FakeResponse()

    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-perplexity-key")

    results = asyncio.run(
        web_search._search_perplexity(FakeSession(), "taipei zoo", 5)
    )

    assert captured == {
        "url": "https://api.perplexity.ai/search",
        "json": {"query": "taipei zoo", "max_results": 5, "max_tokens_per_page": 512},
        "headers": {"Authorization": "Bearer test-perplexity-key"},
    }
    assert [result.url for result in results] == [
        "https://www.zoo.gov.taipei/",
        "https://example.com/long",
    ]
    assert results[0].snippet == "Taipei Zoo is the largest zoo in Taiwan."
    assert len(results[1].snippet) == web_search.PERPLEXITY_SNIPPET_MAX_CHARS


def test_perplexity_search_requires_a_key(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    class FakeSession:
        def post(self, *_args, **_kwargs):  # pragma: no cover - must not be called
            raise AssertionError("request sent without a key")

    try:
        asyncio.run(web_search._search_perplexity(FakeSession(), "query", 3))
    except web_search.HTTPException as error:
        assert error.status_code == 400
        assert "PERPLEXITY_API_KEY" in error.detail
    else:  # pragma: no cover
        raise AssertionError("missing key was accepted")


def test_web_search_context_with_results_tells_failure_from_no_results(monkeypatch):
    async def failing_search(_query, max_results=None):
        raise RuntimeError("provider down")

    monkeypatch.setattr(web_search, "search_web", failing_search)
    assert asyncio.run(web_search.get_web_search_context_with_results("q")) == ("", None)

    async def empty_search(_query, max_results=None):
        return []

    monkeypatch.setattr(web_search, "search_web", empty_search)
    assert asyncio.run(web_search.get_web_search_context_with_results("q")) == ("", [])

    found = [web_search.WebSearchResult("Zoo", "https://example.com/zoo", "Animals")]

    async def found_search(_query, max_results=None):
        return found

    monkeypatch.setattr(web_search, "search_web", found_search)
    context, results = asyncio.run(web_search.get_web_search_context_with_results("q"))
    assert "Animals" in context
    assert results == found
