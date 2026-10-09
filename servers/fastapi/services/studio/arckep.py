"""arckep.ru image API: uploads, async generation jobs, downloads.

Flow (checked live by the standalone Studio, 09.2026): `POST /uploads`
(multipart, ~10 MB) returns a URL for `reference_image_urls`;
`POST /images/generations` returns a job id; `GET /images/generations/{id}`
reports queued|processing|completed|failed with `output.images[].url`.
At most 5 jobs run at once per key.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Callable
from urllib.parse import urlparse

import aiohttp

LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://arckep.ru/api/v1"
REQUEST_TIMEOUT_SECONDS = 60
POLL_BUDGET_SECONDS = 150
FIRST_POLL_DELAY = 1.0
MAX_POLL_DELAY = 3.0


class StudioProviderError(Exception):
    """The provider refused or failed. `detail` is safe to show (no secrets)."""

    def __init__(self, detail: str, status: int | None = None, code: str | None = None):
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.code = code


class StudioTimeoutError(StudioProviderError):
    pass


def _error_detail(payload: Any, fallback: str) -> tuple[str, str | None]:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or fallback)[:300], error.get("code")
        if isinstance(error, str):
            return error[:300], payload.get("code")
        if payload.get("message"):
            return str(payload["message"])[:300], payload.get("code")
    return fallback[:300], None


class ArckepImages:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        poll_budget: float = POLL_BUDGET_SECONDS,
        session_factory: Callable[..., Any] = aiohttp.ClientSession,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._poll_budget = poll_budget
        self._session_factory = session_factory
        self._sleep = sleep

    def _session(self):
        return self._session_factory(
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS),
            headers={"User-Agent": "Presenton-Studio/1.0"},
            trust_env=True,
        )

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def _json(self, response) -> Any:
        text = await response.text()
        try:
            payload = json.loads(text) if text else {}
        except ValueError:
            payload = text
        if response.status >= 400:
            detail, code = _error_detail(payload, str(payload) or f"HTTP {response.status}")
            raise StudioProviderError(detail, status=response.status, code=code)
        return payload

    async def upload(self, session, data: bytes, filename: str = "image.png") -> str:
        form = aiohttp.FormData()
        form.add_field("file", data, filename=filename, content_type="image/png")
        async with session.post(
            f"{self.base_url}/uploads", data=form, headers=self._auth()
        ) as response:
            payload = await self._json(response)
        url = payload.get("url") if isinstance(payload, dict) else None
        if not url:
            raise StudioProviderError("upload returned no URL")
        return str(url)

    async def _download(self, session, url: str) -> bytes:
        # Presigned storage links reject an Authorization header; only the
        # API host itself needs the key.
        same_host = urlparse(url).netloc == urlparse(self.base_url).netloc
        async with session.get(url, headers=self._auth() if same_host else {}) as response:
            if response.status >= 400:
                raise StudioProviderError(f"download failed: HTTP {response.status}", status=response.status)
            return await response.read()

    async def generate(self, body: dict[str, Any], references: list[bytes] | None = None) -> list[bytes]:
        """Run one generation job; returns the images' bytes."""
        async with self._session() as session:
            if references:
                body = {
                    **body,
                    "reference_image_urls": [
                        await self.upload(session, image, f"image-{index}.png")
                        for index, image in enumerate(references)
                    ],
                }
            async with session.post(
                f"{self.base_url}/images/generations",
                json=body,
                headers={**self._auth(), "Idempotency-Key": str(uuid.uuid4())},
            ) as response:
                job = await self._json(response)
            job_id = job.get("id") if isinstance(job, dict) else None
            if job_id is None:
                raise StudioProviderError("no job id in the response")

            deadline = time.monotonic() + self._poll_budget
            delay = FIRST_POLL_DELAY
            while time.monotonic() < deadline:
                await self._sleep(delay)
                delay = min(MAX_POLL_DELAY, delay * 1.4)
                async with session.get(
                    f"{self.base_url}/images/generations/{job_id}", headers=self._auth()
                ) as response:
                    if response.status >= 500:
                        continue
                    status = await self._json(response)
                state = status.get("status") if isinstance(status, dict) else None
                if state == "completed":
                    images = (status.get("output") or {}).get("images") or []
                    urls = [image.get("url") for image in images if isinstance(image, dict) and image.get("url")]
                    if not urls:
                        raise StudioProviderError("the job finished without images")
                    return [await self._download(session, url) for url in urls]
                if state == "failed":
                    detail, code = _error_detail(status, "the job failed")
                    raise StudioProviderError(detail, code=code)
            LOGGER.warning("Studio job %s did not finish in %ss", job_id, self._poll_budget)
            raise StudioTimeoutError("the job did not finish in time")
