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


def test_perplexity_is_the_default_once_its_key_is_configured(monkeypatch):
    monkeypatch.delenv("WEB_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.AUTO

    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-perplexity-key")
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.PERPLEXITY
    assert web_search.get_web_search_route() == ("external", WebSearchProvider.PERPLEXITY)

    # An empty setting (cleared in the UI) also falls back to the default.
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "  ")
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.PERPLEXITY


def test_explicit_provider_wins_over_the_perplexity_default(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "test-perplexity-key")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.TAVILY.value)
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.TAVILY

    monkeypatch.setenv("WEB_SEARCH_PROVIDER", WebSearchProvider.AUTO.value)
    assert web_search.get_selected_web_search_provider() == WebSearchProvider.AUTO


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
