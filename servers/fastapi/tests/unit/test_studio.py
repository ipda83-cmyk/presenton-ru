import asyncio
import base64
import io
import json
import os

import aiohttp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.v1.studio import router as studio_router
from models.sql.image_asset import ImageAsset
from models.sql.user import User
from services.database import get_async_session
from services.studio import arckep, imaging, service
from services.studio.arckep import (
    ArckepImages,
    StudioProviderError,
    StudioTimeoutError,
    StudioUnavailableError,
)
from services.studio.models import MODELS
from utils.i18n.middleware import LocaleMiddleware


def _png(size=(120, 80), color=(255, 0, 0, 255), mode="RGBA") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def _mask(size=(120, 80), box=(10, 30, 20, 40)) -> bytes:
    """Opaque mask with a transparent (to change) box, as the brush draws it."""
    image = Image.new("RGBA", size, (0, 0, 0, 255))
    ImageDraw.Draw(image).rectangle(box, fill=(0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _pixel(png: bytes, xy):
    return Image.open(io.BytesIO(png)).convert("RGB").getpixel(xy)


# --- imaging -------------------------------------------------------------------


def test_compose_masked_changes_only_the_brushed_area():
    original = _png((400, 300), (255, 0, 0, 255))
    result = _png((800, 600), (0, 0, 255, 255))  # models may answer in another size
    mask = _mask((400, 300), (40, 140, 50, 150))

    out = imaging.compose_masked(original, result, mask)

    assert Image.open(io.BytesIO(out)).size == (400, 300)
    assert _pixel(out, (45, 145)) == (0, 0, 255)  # inside the brush
    assert _pixel(out, (390, 10)) == (255, 0, 0)  # far outside stays exact


def test_compose_masked_without_a_selection_returns_the_original():
    original = _png((60, 40), (10, 20, 30, 255))
    empty_mask = _png((60, 40), (0, 0, 0, 255))
    out = imaging.compose_masked(original, _png((60, 40), (200, 200, 200, 255)), empty_mask)
    assert _pixel(out, (30, 20)) == (10, 20, 30)


def test_compose_masked_undoes_a_slight_tone_drift_of_the_redrawn_frame():
    # The live arckep run darkened the whole sky by ~6 levels: a visible halo.
    original = Image.new("RGB", (600, 400), (180, 220, 250))
    ImageDraw.Draw(original).rectangle((0, 300, 599, 399), fill=(80, 150, 90))
    redrawn = original.point([max(0, v - 6) for v in range(256)] * 3)
    ImageDraw.Draw(redrawn).rectangle((280, 150, 320, 190), fill=(250, 220, 10))
    as_png = lambda image: (lambda buffer: (image.save(buffer, "PNG"), buffer.getvalue())[1])(io.BytesIO())

    out = imaging.compose_masked(as_png(original), as_png(redrawn), _mask((600, 400), (280, 150, 320, 190)))

    assert _pixel(out, (300, 170)) == (255, 226, 16)  # the edit, in the original's tone
    for xy in ((250, 170), (300, 120), (375, 170), (300, 245)):  # redrawn or blended, not brushed
        assert all(abs(a - b) <= 1 for a, b in zip(_pixel(out, xy), original.getpixel(xy)))


def test_dilate_grows_a_thin_stroke_even_with_a_large_radius():
    area = Image.new("L", (2000, 1000), 0)
    ImageDraw.Draw(area).line((1000, 500, 1010, 500), fill=255, width=1)
    grown = imaging.dilate(area, 400)
    assert grown.getpixel((1000, 500)) == 255
    assert grown.getpixel((1000, 850)) == 255  # ~350 px away
    assert grown.getpixel((10, 10)) == 0


def test_fit_for_upload_caps_the_longest_side():
    big = _png((3000, 1500), (12, 34, 56, 255), mode="RGBA")
    fitted = imaging.fit_for_upload(big)
    assert max(imaging.image_size(fitted)) <= imaging.UPLOAD_MAX_SIDE
    small = _png((100, 50))
    assert imaging.image_size(imaging.fit_for_upload(small)) == (100, 50)


def test_open_image_rejects_garbage():
    with pytest.raises(imaging.InvalidImageError):
        imaging.open_image(b"not an image")


def test_pick_gpt_size_follows_the_aspect_ratio():
    assert imaging.pick_gpt_size(1920, 1080)[0] == "1536x1024"
    assert imaging.pick_gpt_size(1080, 1920)[0] == "1024x1536"
    assert imaging.pick_gpt_size(1000, 1000)[0] == "1024x1024"


# --- request bodies --------------------------------------------------------------


def test_generation_body_per_model_family():
    gemini = service.generation_body(
        MODELS["nano_banana_pro"], " zoo ", aspect_ratio="16:9", resolution="2K", count=4
    )
    assert gemini == {
        "model": "gemini-3-pro-image",
        "prompt": "zoo",
        "n": 1,
        "aspect_ratio": "16:9",
        "resolution": "2K",
    }
    gpt = service.generation_body(
        MODELS["chatgpt_images_2"], "zoo", aspect_ratio="16:9", quality="high", count=9
    )
    assert gpt == {"model": "gpt-image-2", "prompt": "zoo", "n": 4, "quality": "high"}
    gpt_square = service.generation_body(MODELS["chatgpt_images_2"], "zoo", aspect_ratio="1:1")
    assert gpt_square["size"] == "1024x1024"
    assert gpt_square["quality"] == "medium"


def test_edit_prompt_modes():
    assert service.edit_prompt("x", masked=False, operation="upscale", reference=False).startswith("Upscale")
    masked = service.edit_prompt("add a cup", masked=True, operation=None, reference=False)
    assert "mask" in masked and masked.endswith("add a cup")
    assert "reference" in service.edit_prompt("on the table", masked=False, operation=None, reference=True)


def test_studio_key_falls_back_to_the_search_key_on_the_same_host(monkeypatch):
    monkeypatch.delenv("STUDIO_API_KEY", raising=False)
    monkeypatch.delenv("STUDIO_BASE_URL", raising=False)
    monkeypatch.setenv("GEMINI_SEARCH_API_KEY", "ark-search")
    monkeypatch.setenv("GEMINI_SEARCH_BASE_URL", "https://arckep.ru/api/v1")
    assert service.studio_api_key() == "ark-search"
    assert service.studio_configured()

    monkeypatch.setenv("GEMINI_SEARCH_BASE_URL", "https://other.example/api/v1")
    assert service.studio_api_key() == ""

    monkeypatch.setenv("STUDIO_API_KEY", "ark-studio")
    assert service.studio_api_key() == "ark-studio"


# --- arckep client -----------------------------------------------------------------


class _Response:
    def __init__(self, status=200, payload=None, body=b""):
        self.status = status
        self._payload = payload
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def text(self):
        return json.dumps(self._payload) if self._payload is not None else ""

    async def read(self):
        return self._body


class _FakeArckep:
    """Scripted arckep: answers by (method, url)."""

    def __init__(self, statuses, image=b"PNGDATA"):
        self.calls = []
        self.statuses = list(statuses)
        self.image = image

    def __call__(self, **_kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def post(self, url, json=None, data=None, headers=None):
        self.calls.append(("POST", url, json, headers))
        if url.endswith("/uploads"):
            return _Response(payload={"url": f"https://cdn.example/up-{len(self.calls)}.png"})
        return _Response(payload={"id": 42, "status": "queued"})

    def get(self, url, headers=None):
        self.calls.append(("GET", url, None, headers))
        if "/images/generations/" in url:
            status = self.statuses.pop(0) if self.statuses else {"status": "processing"}
            return _Response(payload=status)
        return _Response(body=self.image)


async def _no_sleep(_seconds):
    return None


def test_arckep_generate_uploads_polls_and_downloads():
    fake = _FakeArckep(
        [
            {"status": "queued"},
            {"status": "completed", "output": {"images": [{"url": "https://cdn.example/out.png"}]}},
        ]
    )
    client = ArckepImages("https://arckep.example/api/v1/", "ark-key", session_factory=fake, sleep=_no_sleep)

    images = asyncio.run(client.generate({"model": "m", "prompt": "p"}, [b"a", b"b"]))

    assert images == [b"PNGDATA"]
    uploads = [call for call in fake.calls if call[1].endswith("/uploads")]
    assert len(uploads) == 2
    create = next(call for call in fake.calls if call[1].endswith("/images/generations"))
    assert create[2]["reference_image_urls"] == [
        "https://cdn.example/up-1.png",
        "https://cdn.example/up-2.png",
    ]
    assert create[3]["Authorization"] == "Bearer ark-key"
    assert create[3]["Idempotency-Key"]
    download = fake.calls[-1]
    # Presigned storage links get no Authorization header.
    assert download[1] == "https://cdn.example/out.png" and download[3] == {}


def test_arckep_failed_job_and_timeout():
    failed = _FakeArckep([{"status": "failed", "error": {"message": "content policy", "code": "MODERATION"}}])
    client = ArckepImages("https://arckep.example/api/v1", "k", session_factory=failed, sleep=_no_sleep)
    with pytest.raises(StudioProviderError) as error:
        asyncio.run(client.generate({"model": "m", "prompt": "p"}))
    assert error.value.detail == "content policy" and error.value.code == "MODERATION"

    slow = _FakeArckep([])
    client = ArckepImages("https://arckep.example/api/v1", "k", poll_budget=0.05, session_factory=slow, sleep=_no_sleep)
    with pytest.raises(StudioTimeoutError):
        asyncio.run(client.generate({"model": "m", "prompt": "p"}))


def test_arckep_http_errors_carry_status_and_message():
    class Refusing(_FakeArckep):
        def post(self, url, json=None, data=None, headers=None):
            return _Response(status=402, payload={"error": {"message": "Недостаточно средств", "code": "INSUFFICIENT_BALANCE"}})

    client = ArckepImages("https://a.example/api/v1", "k", session_factory=Refusing([]), sleep=_no_sleep)
    with pytest.raises(StudioProviderError) as error:
        asyncio.run(client.generate({"model": "m", "prompt": "p"}))
    assert error.value.status == 402 and error.value.code == "INSUFFICIENT_BALANCE"


class _BusyArckep(_FakeArckep):
    """Counts jobs running at once; a job completes on its second poll."""

    def __init__(self, busy_answers=0):
        super().__init__([])
        self.busy_answers = busy_answers
        self.polls: dict[int, int] = {}
        self.active = 0
        self.max_active = 0

    def post(self, url, json=None, data=None, headers=None):
        self.calls.append(("POST", url, json, headers))
        if self.busy_answers:
            self.busy_answers -= 1
            return _Response(status=429, payload={"error": {"message": "too many active jobs"}})
        job_id = len(self.calls)
        self.polls[job_id] = 0
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        return _Response(payload={"id": job_id, "status": "queued"})

    def get(self, url, headers=None):
        self.calls.append(("GET", url, None, headers))
        if "/images/generations/" not in url:
            return _Response(body=self.image)
        job_id = int(url.rsplit("/", 1)[-1])
        self.polls[job_id] += 1
        if self.polls[job_id] < 2:
            return _Response(payload={"status": "processing"})
        self.active -= 1
        return _Response(payload={"status": "completed", "output": {"images": [{"url": "https://cdn.example/o.png"}]}})


async def _yield(_seconds):
    await asyncio.sleep(0)


def test_arckep_jobs_wait_for_a_free_slot_instead_of_failing(monkeypatch):
    # All users share one key and arckep runs at most 5 jobs per key.
    monkeypatch.setattr(arckep, "MAX_ACTIVE_JOBS", 2)
    monkeypatch.setattr(arckep, "_job_slots", None)
    fake = _BusyArckep()
    client = ArckepImages("https://arckep.example/api/v1", "k", session_factory=fake, sleep=_yield)

    async def many():
        return await asyncio.gather(*(client.generate({"model": "m", "prompt": str(i)}) for i in range(5)))

    assert asyncio.run(many()) == [[b"PNGDATA"]] * 5
    assert fake.max_active == 2


def test_arckep_retries_a_busy_answer():
    waits = []

    async def record(seconds):
        waits.append(seconds)

    fake = _BusyArckep(busy_answers=2)
    client = ArckepImages("https://arckep.example/api/v1", "k", session_factory=fake, sleep=record)
    assert asyncio.run(client.generate({"model": "m", "prompt": "p"})) == [b"PNGDATA"]
    assert waits[:2] == list(arckep.BUSY_RETRY_DELAYS[:2])
    creates = [call for call in fake.calls if call[0] == "POST"]
    assert len({call[3]["Idempotency-Key"] for call in creates}) == 3

    always_busy = _BusyArckep(busy_answers=99)
    client = ArckepImages("https://arckep.example/api/v1", "k", session_factory=always_busy, sleep=_no_sleep)
    with pytest.raises(StudioProviderError) as error:
        asyncio.run(client.generate({"model": "m", "prompt": "p"}))
    assert error.value.status == 429


def test_arckep_network_failures():
    class Unreachable(_FakeArckep):
        def post(self, url, json=None, data=None, headers=None):
            raise aiohttp.ClientConnectionError("Temporary failure in name resolution")

    client = ArckepImages("https://arckep.example/api/v1", "k", session_factory=Unreachable([]), sleep=_no_sleep)
    with pytest.raises(StudioUnavailableError):
        asyncio.run(client.generate({"model": "m", "prompt": "p"}, [b"ref"]))

    class DroppedPoll(_FakeArckep):
        dropped = False

        def get(self, url, headers=None):
            if "/images/generations/" in url and not self.dropped:
                self.dropped = True
                raise asyncio.TimeoutError()
            return super().get(url, headers)

    flaky = DroppedPoll([{"status": "completed", "output": {"images": [{"url": "https://cdn.example/o.png"}]}}])
    client = ArckepImages("https://arckep.example/api/v1", "k", session_factory=flaky, sleep=_no_sleep)
    assert asyncio.run(client.generate({"model": "m", "prompt": "p"})) == [b"PNGDATA"]


class _ScriptedClient:
    def __init__(self, result: bytes):
        self.result = result
        self.calls = []

    async def generate(self, body, references=None):
        self.calls.append((body, references))
        return [self.result]


def test_edit_image_with_a_mask_keeps_the_outside_and_sends_a_matching_mask():
    original = _png((200, 100), (255, 0, 0, 255))
    client = _ScriptedClient(_png((200, 100), (0, 255, 0, 255)))

    out = asyncio.run(
        service.edit_image(
            MODELS["nano_banana_2"], original, "make it green", mask=_mask((200, 100), (20, 40, 30, 50)), client=client
        )
    )

    body, references = client.calls[0]
    assert body["model"] == "gemini-3.1-flash-image"
    assert "mask" in body["prompt"]
    assert len(references) == 2
    assert imaging.image_size(references[1]) == imaging.image_size(references[0])
    assert _pixel(out, (25, 45)) == (0, 255, 0)
    assert _pixel(out, (195, 5)) == (255, 0, 0)


def test_edit_image_for_gpt_uses_a_supported_size():
    client = _ScriptedClient(_png((1536, 1024)))
    asyncio.run(
        service.edit_image(MODELS["chatgpt_images_2"], _png((1920, 1080)), "", operation="upscale", client=client)
    )
    body, references = client.calls[0]
    assert body["size"] == "1536x1024"
    assert body["prompt"].startswith("Upscale")
    assert imaging.image_size(references[0]) == (1536, 1024)


# --- API -----------------------------------------------------------------------------


@pytest.fixture
def studio_api(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("DISABLE_AUTH", "true")
    monkeypatch.setenv("STUDIO_API_KEY", "ark-test")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'studio.db'}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(User.__table__.create)
            await connection.run_sync(ImageAsset.__table__.create)

    asyncio.run(create())

    async def override():
        async with session_maker() as session:
            yield session

    app = FastAPI()
    app.add_middleware(LocaleMiddleware)
    app.include_router(studio_router.API_V1_STUDIO_ROUTER)
    app.dependency_overrides[get_async_session] = override
    yield TestClient(app), tmp_path
    asyncio.run(engine.dispose())


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def test_api_generate_edit_history_and_delete(studio_api, monkeypatch):
    client, tmp_path = studio_api

    async def fake_create(model, prompt, **kwargs):
        return [_png((64, 64), (1, 2, 3, 255))]

    async def fake_edit(model, source, prompt="", **kwargs):
        return _png((64, 64), (9, 9, 9, 255))

    monkeypatch.setattr(studio_router, "create_images", fake_create)
    monkeypatch.setattr(studio_router, "edit_image", fake_edit)

    config = client.get("/api/v1/studio/config").json()
    assert config["configured"] is True
    assert {model["key"] for model in config["models"]} == set(MODELS)
    assert {model["family"] for model in config["models"]} == {"gemini", "gpt"}

    created = client.post("/api/v1/studio/generate", json={"prompt": "зоопарк", "aspect_ratio": "16:9"})
    assert created.status_code == 200
    image = created.json()["images"][0]
    assert image["file_url"].startswith("/app_data/images/")
    assert image["extras"]["mode"] == "create"
    assert os.path.isfile(os.path.join(tmp_path, image["file_url"][len("/app_data/"):]))

    # Edit an existing image by its app_data URL.
    edited = client.post(
        "/api/v1/studio/edit", json={"image": image["file_url"], "prompt": "светлее"}
    )
    assert edited.status_code == 200
    assert edited.json()["image"]["extras"]["parent"] == image["file_url"]

    # A reference insert needs no prompt: the object is the instruction.
    inserted = client.post(
        "/api/v1/studio/edit",
        json={"image": image["file_url"], "reference": _data_url(_png()), "mask": _data_url(_mask((64, 64), (5, 5, 20, 20)))},
    )
    assert inserted.status_code == 200
    assert inserted.json()["image"]["extras"]["mode"] == "reference"

    history = client.get("/api/v1/studio/history").json()["images"]
    assert [item["extras"]["mode"] for item in history] == ["reference", "edit", "create"]

    deleted = client.delete(f"/api/v1/studio/history/{image['id']}")
    assert deleted.status_code == 204
    assert not os.path.exists(os.path.join(tmp_path, image["file_url"][len("/app_data/"):]))
    assert len(client.get("/api/v1/studio/history").json()["images"]) == 2


def test_api_validation_and_localized_errors(studio_api, monkeypatch):
    client, _ = studio_api
    ru = {"Cookie": "NEXT_LOCALE=ru"}

    no_prompt = client.post("/api/v1/studio/edit", json={"image": _data_url(_png())}, headers=ru)
    assert no_prompt.status_code == 400
    assert no_prompt.json()["detail"] == "Опишите, что изменить."

    bad_image = client.post("/api/v1/studio/edit", json={"image": "data:image/png;base64,AAAA", "prompt": "x"}, headers=ru)
    assert bad_image.status_code == 400

    missing = client.post("/api/v1/studio/edit", json={"image": "/app_data/images/nope.png", "prompt": "x"})
    assert missing.status_code == 404

    unknown = client.post("/api/v1/studio/generate", json={"prompt": "x", "model": "dalle"})
    assert unknown.status_code == 400

    async def broke(model, prompt, **kwargs):
        raise StudioProviderError("Недостаточно средств", status=402, code="INSUFFICIENT_BALANCE")

    monkeypatch.setattr(studio_router, "create_images", broke)
    poor = client.post("/api/v1/studio/generate", json={"prompt": "x"}, headers=ru)
    assert poor.status_code == 503  # the service balance; 402 is the user's own
    assert "баланс" in poor.json()["detail"]

    async def no_scope(model, prompt, **kwargs):
        raise StudioProviderError(
            "API key is missing required scope 'images:write'. Create a new key with this scope.",
            status=403,
        )

    monkeypatch.setattr(studio_router, "create_images", no_scope)
    scope = client.post("/api/v1/studio/generate", json={"prompt": "x"}, headers=ru)
    assert scope.status_code == 502
    assert "images:write" in scope.json()["detail"] and "права" in scope.json()["detail"]

    async def unreachable(model, prompt, **kwargs):
        raise StudioUnavailableError("arckep is unreachable")

    monkeypatch.setattr(studio_router, "create_images", unreachable)
    down = client.post("/api/v1/studio/generate", json={"prompt": "x"}, headers=ru)
    assert down.status_code == 503
    assert "недоступен" in down.json()["detail"]

    monkeypatch.delenv("STUDIO_API_KEY")
    monkeypatch.delenv("GEMINI_SEARCH_API_KEY", raising=False)
    not_set = client.post("/api/v1/studio/generate", json={"prompt": "x"}, headers=ru)
    assert not_set.status_code == 409
    assert "ключ arckep" in not_set.json()["detail"]


def test_api_edit_accepts_only_app_pictures_and_public_urls(studio_api, monkeypatch):
    client, tmp_path = studio_api

    async def fake_edit(model, source, prompt="", **kwargs):
        return _png((32, 32), (5, 5, 5, 255))

    monkeypatch.setattr(studio_router, "edit_image", fake_edit)

    # Other files on the server are not pictures of the user's.
    for path in ("/etc/hosts", "/app/servers/fastapi/static/../../../etc/hosts", "relative/x.png"):
        assert client.post("/api/v1/studio/edit", json={"image": path, "prompt": "x"}).status_code == 404

    # Internal addresses are never requested (SSRF).
    for url in ("http://127.0.0.1:9/x.png", "http://localhost/x.png", "http://10.0.0.1/x.png"):
        assert client.post("/api/v1/studio/edit", json={"image": url, "prompt": "x"}).status_code == 404

    # A stock photo on a public site is downloaded first.
    fetched = []

    async def fake_download(url):
        fetched.append(url)
        return _png((40, 30), (200, 100, 0, 255))

    monkeypatch.setattr(studio_router, "_download_public_image", fake_download)
    stock = client.post("/api/v1/studio/edit", json={"image": "https://images.example.com/p.jpg", "prompt": "x"})
    assert stock.status_code == 200
    assert fetched == ["https://images.example.com/p.jpg"]


def test_api_storyboard_makes_one_view_of_the_reference(studio_api, monkeypatch):
    client, tmp_path = studio_api
    seen = {}

    async def fake_edit(model, source, prompt="", **kwargs):
        seen.update(model=model.key, prompt=prompt, kwargs=kwargs)
        return _png((48, 64), (20, 40, 60, 255))

    monkeypatch.setattr(studio_router, "edit_image", fake_edit)
    config = client.get("/api/v1/studio/config").json()
    assert [view["id"] for view in config["storyboard_views"]][:2] == ["front", "three_quarter_left"]

    response = client.post(
        "/api/v1/studio/storyboard",
        json={"image": _data_url(_png()), "view": "profile_left", "model": "nano_banana_pro", "resolution": "2K", "details": "в шлеме"},
    )
    assert response.status_code == 200
    image = response.json()["image"]
    assert image["extras"]["mode"] == "storyboard"
    assert image["extras"]["view"] == "profile_left"
    assert seen["model"] == "nano_banana_pro"
    assert "left side profile view" in seen["prompt"] and "SAME character" in seen["prompt"]
    assert seen["prompt"].endswith("Additional details: в шлеме")
    assert seen["kwargs"]["resolution"] == "2K"


def test_api_storyboard_validation(studio_api):
    client, _ = studio_api
    ru = {"Cookie": "NEXT_LOCALE=ru"}
    unknown = client.post("/api/v1/studio/storyboard", json={"image": _data_url(_png()), "view": "upside_down"}, headers=ru)
    assert unknown.status_code == 400
    assert "upside_down" in unknown.json()["detail"]
    gpt = client.post(
        "/api/v1/studio/storyboard",
        json={"image": _data_url(_png()), "view": "front", "model": "chatgpt_images_2"},
        headers=ru,
    )
    assert gpt.status_code == 400
    assert "Gemini" in gpt.json()["detail"]

