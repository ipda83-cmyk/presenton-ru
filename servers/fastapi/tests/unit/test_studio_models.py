"""Studio image models from arckep's catalog, chosen in Admin → Models."""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.studio import admin_router
from services.studio import catalog, estimates, service
from services.studio import models as studio_models
from services.studio.models import (
    REGISTRY,
    default_settings,
    enabled_models,
    get_model,
    load_snapshot,
    supported_modes,
)
from utils.i18n.middleware import LocaleMiddleware


def test_the_starting_set():
    keys = [model.key for model in enabled_models()]
    assert keys == [
        "gemini-nano-banana-2.1",
        "gemini-3-pro-image",
        "gpt-image-2.5-sunburst",
        "flux-2-pro",
        "seedream-5.0-pro",
        "recraft-v4.1-vector",
    ]
    assert get_model(None).key == "gemini-nano-banana-2.1"
    assert get_model("nano_banana_pro").title == "Nano Banana Pro"  # old keys keep working
    assert get_model("nano_banana_2").key == "gemini-nano-banana-2.1"
    assert get_model("midjourney") is None  # in the catalog, off until turned on
    assert get_model("midjourney", include_disabled=True).quality_levels == ("fast", "turbo", "relax")
    assert len(REGISTRY.all) == 37


def test_modes_follow_the_catalog():
    by_id = {entry["id"]: entry for entry in load_snapshot()}
    assert supported_modes(by_id["gemini-3-pro-image"]) == ("generate", "edit", "reference", "storyboard")
    assert supported_modes(by_id["qwen-image-edit"]) == ("storyboard",)  # edits only, one reference
    assert supported_modes(by_id["qwen-image-plus"]) == ("generate",)  # no references at all
    assert "storyboard" in get_model("gemini-3-pro-image").modes
    gpt = get_model("gpt-image-2.5-sunburst")
    assert "storyboard" in gpt.supported_modes and "storyboard" not in gpt.modes  # Gemini only by default
    assert gpt.max_count == 4 and gpt.resolve_quality("draft") == "low" and gpt.resolve_quality(None) == "medium"


def test_generic_request_bodies():
    flux = service.generation_body(get_model("flux-2-pro"), "кот", aspect_ratio="16:9", resolution="2K", count=3)
    assert flux == {"model": "flux-2-pro", "prompt": "кот", "n": 1, "aspect_ratio": "16:9", "resolution": "2K"}
    mj = get_model("midjourney", include_disabled=True)
    assert service.generation_body(mj, "кот", aspect_ratio="21:9", quality="turbo")["quality"] == "turbo"
    assert "aspect_ratio" not in service.generation_body(mj, "кот", aspect_ratio="21:9")
    gpt = service.generation_body(get_model("gpt-image-2.5-sunburst"), "кот", aspect_ratio="3:2", quality="max", count=2)
    assert gpt == {"model": "gpt-image-2.5-sunburst", "prompt": "кот", "n": 2, "size": "1536x1024", "quality": "max"}


def test_settings_are_cleaned_up():
    settings = default_settings()
    settings["models"]["midjourney"] = {"enabled": True, "title": "  Midjourney   v7 ", "modes": ["generate", "fly"], "order": "x"}
    settings["models"]["not-a-model"] = {"enabled": True}
    settings["models"]["flux-2-pro"]["modes"] = ["generate", "storyboard"]
    settings["markup"] = -3
    settings["slide_image_model"] = "nope"
    REGISTRY.apply(load_snapshot(), settings)
    mj = get_model("midjourney")
    assert mj.title == "Midjourney v7" and mj.modes == ("generate",) and mj.order == 0
    assert "not-a-model" not in REGISTRY.settings["models"]
    assert get_model("flux-2-pro").modes == ("generate", "storyboard")  # the administrator's choice
    assert REGISTRY.settings["markup"] == 1.45 and REGISTRY.settings["slide_image_model"] == ""


def test_catalog_answer_and_refresh(monkeypatch):
    payload = {
        "object": "list",
        "data": [
            {"id": "new-image-model", "type": "image", "name": "New", "provider": "acme", "modes": ["generate"], "aspect_ratios": ["1:1"], "extra": 1},
            {"id": "some-chat", "type": "chat"},
        ],
    }
    assert catalog.image_models_from_catalog(payload) == [
        {field: payload["data"][0].get(field) for field in catalog.CATALOG_FIELDS}
    ]
    stored = {}

    async def fetch():
        return load_snapshot() + catalog.image_models_from_catalog(payload)

    async def write(key, value):
        stored[key] = value

    monkeypatch.setattr(catalog, "fetch_catalog", fetch)
    monkeypatch.setattr(catalog, "_write", write)
    monkeypatch.setenv("STUDIO_API_KEY", "arckep-key")
    asyncio.run(catalog.load(refresh_catalog=True))
    assert get_model("new-image-model", include_disabled=True).title == "New"
    assert catalog.catalog_state()["source"] == "arckep" and catalog.catalog_state()["count"] == 38
    assert len(stored["studio:catalog"]["models"]) == 38


def _admin_client():
    app = FastAPI()
    app.add_middleware(LocaleMiddleware)
    app.include_router(admin_router.API_V1_ADMIN_STUDIO_ROUTER)
    return TestClient(app)


def test_admin_turns_models_on_and_sets_names_modes_and_prices(monkeypatch):
    saved = {}

    async def write(key, value):
        saved[key] = value

    monkeypatch.setattr(catalog, "_write", write)
    client = _admin_client()
    state = client.get("/api/v1/admin/studio/models").json()
    assert state["default_model"] == "gemini-nano-banana-2.1" and state["markup"] == 1.45
    rows = {row["key"]: row for row in state["models"]}
    assert [row["key"] for row in state["models"][:6]] == [model.key for model in enabled_models()]
    assert rows["gemini-3-pro-image"]["costs"]["1K|"]["source"] == "known"
    assert rows["gemini-3-pro-image"]["costs"]["1K|"]["price"] == 25
    assert rows["flux-2-pro"]["costs"]["1K|"]["source"] == "none"

    body = {
        "default_model": "gemini-3-pro-image",
        "markup": 1.5,
        "slide_image_model": "flux-2-pro",
        "models": {
            "gemini-3-pro-image": {"enabled": True, "title": "Nano Banana Pro", "order": 0},
            "midjourney": {"enabled": True, "title": "Midjourney", "order": 1, "modes": ["generate"], "costs": {"1K|fast": 9}},
            "flux-2-pro": {"enabled": False},
        },
    }
    state = client.put("/api/v1/admin/studio/models", json=body).json()
    assert [model.key for model in enabled_models()] == ["gemini-3-pro-image", "midjourney"]
    assert get_model("flux-2-pro") is None and REGISTRY.slide_image_model().key == "flux-2-pro"
    assert saved["studio:models"]["markup"] == 1.5
    mj = {row["key"]: row for row in state["models"]}["midjourney"]
    assert mj["costs"]["1K|fast"] == {**mj["costs"]["1K|fast"], "source": "manual", "cost": 9.0, "price": 14}

    unknown = client.put("/api/v1/admin/studio/models", json={**body, "models": {"dall-e-9": {"enabled": True}}})
    assert unknown.status_code == 400


def test_admin_asks_arckep_for_a_model_price_again(monkeypatch):
    monkeypatch.setenv("STUDIO_API_KEY", "arckep-key")
    asked = []

    async def fake(model, resolution, quality):
        asked.append((resolution, quality))
        return 2.0, {"cost_rub": 2.0}

    monkeypatch.setattr(estimates, "_request", fake)
    row = _admin_client().post("/api/v1/admin/studio/models/flux-2-pro/estimate").json()
    assert sorted(asked) == [("1K", None), ("2K", None)]
    assert row["costs"]["2K|"]["source"] == "estimate" and row["costs"]["2K|"]["estimate_raw"] == {"cost_rub": 2.0}
    assert _admin_client().post("/api/v1/admin/studio/models/unknown/estimate").status_code == 404


def test_slide_pictures_by_the_chosen_studio_model(monkeypatch, tmp_path):
    from services import image_generation_service as images

    settings = default_settings()
    settings["slide_image_model"] = "seedream-5.0-pro"
    REGISTRY.apply(load_snapshot(), settings)
    monkeypatch.setenv("STUDIO_API_KEY", "arckep-key")
    monkeypatch.delenv("DISABLE_IMAGE_GENERATION", raising=False)
    calls = []

    async def fake_create(model, prompt, **kwargs):
        calls.append((model.key, prompt, kwargs))
        return [b"PNG slide"]

    monkeypatch.setattr(service, "create_images", fake_create)
    generator = images.ImageGenerationService(str(tmp_path))
    assert generator.image_gen_func == generator.generate_image_studio
    path = asyncio.run(generator.generate_image_studio("город будущего", str(tmp_path)))
    assert open(path, "rb").read() == b"PNG slide"
    assert calls == [("seedream-5.0-pro", "город будущего", {"aspect_ratio": "16:9", "resolution": "1K", "quality": None})]

    # Without a chosen model the provider settings decide, as before.
    REGISTRY.apply(load_snapshot())
    assert images.ImageGenerationService(str(tmp_path)).image_gen_func != generator.generate_image_studio


def test_studio_config_shows_only_enabled_models(monkeypatch, tmp_path):
    from api.v1.studio import router as studio_router

    monkeypatch.setenv("DISABLE_AUTH", "true")
    app = FastAPI()
    app.add_middleware(LocaleMiddleware)
    app.include_router(studio_router.API_V1_STUDIO_ROUTER)
    settings = default_settings()
    settings["models"] = {"recraft-v4.1-vector": {"enabled": True, "title": "Векторы"}}
    settings["default_model"] = "gemini-3-pro-image"  # turned off: the first enabled one is used
    REGISTRY.apply(load_snapshot(), settings)
    config = TestClient(app).get("/api/v1/studio/config").json()
    assert [model["title"] for model in config["models"]] == ["Векторы"]
    assert config["default_model"] == "recraft-v4.1-vector"
    assert set(config["models"][0]["modes"]) == {"generate", "edit", "reference"}
    assert studio_models.MODES == ("generate", "edit", "reference", "storyboard")
