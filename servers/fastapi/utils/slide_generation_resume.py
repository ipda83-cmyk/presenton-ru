"""Keep a presentation's slide generation going through a flaky model.

The standard stream saves slides only when every slide is done, and the
browser reconnects after an error, which used to start over from slide 1: with
a provider that times out or answers empty every minute or so the user saw the
deck reach slide 4, drop back to 1, and spin forever.

Two remedies:
- a slide whose model call fails transiently (timeout, 5xx, rate limit, empty
  answer) is tried again after a pause before the stream gives up;
- slides already written (and their pictures) are remembered in this process
  for a while, so a reconnect replays them at once and continues from the
  slide that failed.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Optional, TypeVar

from fastapi import HTTPException

from utils.i18n import t

LOGGER = logging.getLogger(__name__)

TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
RETRY_DELAYS_SECONDS = (3.0, 8.0)  # two more tries after the first failure
RESUME_TTL_SECONDS = 2 * 60 * 60
RESUME_MAX_PRESENTATIONS = 64

T = TypeVar("T")


def is_transient_llm_error(error: BaseException) -> bool:
    if not isinstance(error, HTTPException):
        return False
    if error.status_code in TRANSIENT_STATUSES:
        return True
    # Empty answers come back as 400 with this (localized) text.
    return error.status_code == 400 and error.detail == t("err.llmUtils.llmDidNotReturnAnyContent")


async def with_transient_retries(
    call: Callable[[], Awaitable[T]],
    *,
    label: str,
    delays: Optional[tuple[float, ...]] = None,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> T:
    delays = RETRY_DELAYS_SECONDS if delays is None else delays
    for attempt in range(len(delays) + 1):
        try:
            return await call()
        except HTTPException as error:
            if attempt >= len(delays) or not is_transient_llm_error(error):
                raise
            LOGGER.warning(
                "Model call failed transiently (%s, attempt %d/%d): %s %s",
                label,
                attempt + 1,
                len(delays) + 1,
                error.status_code,
                error.detail,
            )
            await sleep(delays[attempt])
    raise AssertionError("unreachable")


class _ResumeEntry:
    def __init__(self, signature: str):
        self.signature = signature
        self.touched = time.monotonic()
        # slide index -> {"content": dict, "assets": list | None}
        self.slides: dict[int, dict[str, Any]] = {}


class SlideResumeCache:
    """Per-process memory of slides written for unfinished generations."""

    def __init__(self, ttl: float = RESUME_TTL_SECONDS, limit: int = RESUME_MAX_PRESENTATIONS):
        self._ttl = ttl
        self._limit = limit
        self._entries: "OrderedDict[str, _ResumeEntry]" = OrderedDict()

    @staticmethod
    def signature(**parts: Any) -> str:
        """Same outline, layouts and settings -> same slides may be reused."""
        payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _expire(self) -> None:
        now = time.monotonic()
        for key in [key for key, entry in self._entries.items() if now - entry.touched > self._ttl]:
            del self._entries[key]

    def session(self, key: str, signature: str) -> "_ResumeSession":
        self._expire()
        entry = self._entries.get(key)
        if entry is None or entry.signature != signature:
            entry = _ResumeEntry(signature)
            self._entries[key] = entry
        entry.touched = time.monotonic()
        self._entries.move_to_end(key)
        while len(self._entries) > self._limit:
            self._entries.popitem(last=False)
        return _ResumeSession(self, key, entry)

    def forget(self, key: str) -> None:
        self._entries.pop(key, None)


class _ResumeSession:
    def __init__(self, cache: SlideResumeCache, key: str, entry: _ResumeEntry):
        self._cache = cache
        self._key = key
        self._entry = entry

    def content(self, index: int) -> Optional[dict]:
        saved = self._entry.slides.get(index)
        return copy.deepcopy(saved["content"]) if saved else None

    def assets(self, index: int) -> Optional[list]:
        """Pictures already fetched for the slide (its content then has them)."""
        saved = self._entry.slides.get(index)
        return list(saved["assets"]) if saved and saved.get("assets") is not None else None

    def remember_content(self, index: int, content: dict) -> None:
        self._entry.touched = time.monotonic()
        self._entry.slides[index] = {"content": copy.deepcopy(content), "assets": None}

    def remember_assets(self, index: int, content: dict, assets: list) -> None:
        self._entry.touched = time.monotonic()
        self._entry.slides[index] = {"content": copy.deepcopy(content), "assets": list(assets)}

    def finish(self) -> None:
        self._cache.forget(self._key)


SLIDE_RESUME_CACHE = SlideResumeCache()
