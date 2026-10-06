import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models.sql.key_value import KeyValueSqlModel
from utils.web_search import WebSearchResult
from utils.web_sources import (
    SNIPPET_MAX_CHARS,
    build_web_sources_record,
    delete_web_sources,
    get_web_sources,
    save_web_sources,
    web_sources_key,
)


def test_record_keeps_only_real_web_pages_once():
    record = build_web_sources_record(
        status="ok",
        provider="perplexity",
        query="taipei zoo",
        results=[
            WebSearchResult("Taipei Zoo", "https://www.zoo.gov.taipei/en", "Largest zoo."),
            WebSearchResult("Duplicate", "https://www.zoo.gov.taipei/en", "again"),
            WebSearchResult("Script", "javascript:alert(1)", "x"),
            WebSearchResult("FTP", "ftp://files.example.com/a", "x"),
            WebSearchResult("No host", "https:///path", "x"),
            WebSearchResult("Long", "http://example.com/long", "y" * 1000),
        ],
    )

    assert record["status"] == "ok"
    assert record["provider"] == "perplexity"
    assert record["query"] == "taipei zoo"
    assert [source["url"] for source in record["sources"]] == [
        "https://www.zoo.gov.taipei/en",
        "http://example.com/long",
    ]
    assert record["sources"][0]["domain"] == "zoo.gov.taipei"
    assert record["sources"][0]["snippet"] == "Largest zoo."
    assert len(record["sources"][1]["snippet"]) == SNIPPET_MAX_CHARS
    assert record["sources"][1]["snippet"].endswith("…")


def test_unknown_status_is_reported_as_failed():
    assert build_web_sources_record(status="weird")["status"] == "failed"
    assert build_web_sources_record(status="none")["sources"] == []


def _session_maker(tmp_path, *, with_table=True):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sources.db'}")

    async def create():
        if with_table:
            async with engine.begin() as connection:
                await connection.run_sync(KeyValueSqlModel.__table__.create)

    asyncio.run(create())
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def test_save_get_delete_round_trip(tmp_path):
    engine, session_maker = _session_maker(tmp_path)
    first = build_web_sources_record(
        status="ok", results=[WebSearchResult("A", "https://a.example/", "a")]
    )
    second = build_web_sources_record(status="empty")

    async def run():
        async with session_maker() as session:
            assert await get_web_sources(session, "p1") is None
            await save_web_sources(session, "p1", first)
            saved = await get_web_sources(session, "p1")
            assert saved["sources"][0]["url"] == "https://a.example/"
            # Regenerating the outline replaces the previous record.
            await save_web_sources(session, "p1", second)
            assert (await get_web_sources(session, "p1"))["status"] == "empty"
            await delete_web_sources(session, "p1")
            assert await get_web_sources(session, "p1") is None
        await engine.dispose()

    asyncio.run(run())
    assert web_sources_key("p1") == "web_sources:p1"


def test_storage_is_best_effort_without_the_table(tmp_path):
    engine, session_maker = _session_maker(tmp_path, with_table=False)

    async def run():
        async with session_maker() as session:
            await save_web_sources(session, "p1", build_web_sources_record(status="ok"))
            assert await get_web_sources(session, "p1") is None
            await delete_web_sources(session, "p1")
        await engine.dispose()

    asyncio.run(run())
