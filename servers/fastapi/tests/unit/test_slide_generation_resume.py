import asyncio

import pytest
from fastapi import HTTPException

from utils import slide_generation_resume as resume_module
from utils.i18n import t
from utils.slide_generation_resume import SlideResumeCache, is_transient_llm_error, with_transient_retries


def _run(coroutine):
    return asyncio.run(coroutine)


def test_transient_errors_are_timeouts_overload_and_empty_answers():
    assert is_transient_llm_error(HTTPException(504, "Request timed out"))
    assert is_transient_llm_error(HTTPException(429, "slow down"))
    assert is_transient_llm_error(HTTPException(400, t("err.llmUtils.llmDidNotReturnAnyContent")))
    assert not is_transient_llm_error(HTTPException(400, "bad schema"))
    assert not is_transient_llm_error(HTTPException(401, "bad key"))
    assert not is_transient_llm_error(ValueError("not http"))


def test_retries_transient_failures_then_succeeds():
    calls, pauses = [], []

    async def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise HTTPException(504, "Request timed out")
        return {"ok": True}

    async def sleep(seconds):
        pauses.append(seconds)

    assert _run(with_transient_retries(flaky, label="slide 4", sleep=sleep)) == {"ok": True}
    assert len(calls) == 3
    assert pauses == list(resume_module.RETRY_DELAYS_SECONDS)


def test_gives_up_after_the_last_try_and_never_retries_real_errors():
    calls = []

    async def down():
        calls.append(1)
        raise HTTPException(502, "provider down")

    async def no_sleep(_seconds):
        return None

    with pytest.raises(HTTPException):
        _run(with_transient_retries(down, label="slide", sleep=no_sleep))
    assert len(calls) == len(resume_module.RETRY_DELAYS_SECONDS) + 1

    calls.clear()

    async def bad_key():
        calls.append(1)
        raise HTTPException(401, "bad key")

    with pytest.raises(HTTPException):
        _run(with_transient_retries(bad_key, label="slide", sleep=no_sleep))
    assert len(calls) == 1


def test_resume_cache_replays_slides_of_the_same_generation_only():
    cache = SlideResumeCache()
    signature = SlideResumeCache.signature(structure=[0, 1], outline=["a", "b"])
    first = cache.session("user:deck", signature)
    content = {"title": "A", "image": {"image_url": "/static/images/placeholder.jpg"}}
    first.remember_content(0, content)
    content["title"] = "changed afterwards"  # stored as a copy

    again = cache.session("user:deck", signature)
    assert again.content(0) == {"title": "A", "image": {"image_url": "/static/images/placeholder.jpg"}}
    assert again.assets(0) is None  # pictures still to fetch
    again.remember_assets(0, {"title": "A", "image": {"image_url": "/app_data/images/x.png"}}, ["asset"])
    assert cache.session("user:deck", signature).assets(0) == ["asset"]

    # Edited outline: nothing is reused.
    edited = SlideResumeCache.signature(structure=[0, 1], outline=["a", "B"])
    other = cache.session("user:deck", edited)
    assert other.content(0) is None

    other.remember_content(1, {"x": 1})
    other.finish()
    assert cache.session("user:deck", edited).content(1) is None


def test_resume_cache_is_bounded():
    cache = SlideResumeCache(ttl=60, limit=2)
    for name in ("a", "b", "c"):
        cache.session(name, "s").remember_content(0, {"n": name})
    assert cache.session("a", "s").content(0) is None  # evicted (oldest)
    assert cache.session("c", "s").content(0) == {"n": "c"}

    expired = SlideResumeCache(ttl=0, limit=10)
    expired.session("x", "s").remember_content(0, {"n": 1})
    assert expired.session("x", "s").content(0) is None
