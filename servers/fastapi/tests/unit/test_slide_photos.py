import asyncio
import io
import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.v1.ppt.endpoints import outlines as outlines_router
from models.presentation_layout import PresentationLayoutModel, SlideLayoutModel
from models.presentation_outline_model import PresentationOutlineModel, SlideOutlineModel
from models.presentation_structure_model import PresentationStructureModel
from models.sql.key_value import KeyValueSqlModel
from models.sql.presentation import PresentationModel, PresentationVersion
from models.sql.user import User
from services.database import get_async_session
from utils import slide_photos
from utils.i18n.middleware import LocaleMiddleware

# Shapes as built from a real template (see _build_template_layout_model).
IMAGE_LAYOUT = {
    "type": "object",
    "properties": {
        "left_image_block": {
            "type": "object",
            "properties": {"left_media_image": {"type": "object", "properties": {"image_prompt": {"type": "string"}}}},
        },
        "right_text_stack": {"type": "object", "properties": {"stack_heading": {"type": "string"}}},
    },
}
TWO_IMAGE_LAYOUT = {
    "type": "object",
    "properties": {
        "upper": {"type": "object", "properties": {"image_prompt": {"type": "string"}}},
        "lower": {"type": "object", "properties": {"image_prompt": {"type": "string"}}},
    },
}
TEXT_LAYOUT = {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}}}
LEGACY_IMAGE_LAYOUT = {
    "type": "object",
    "properties": {"image": {"type": "object", "properties": {"__image_url__": {}, "__image_prompt__": {}}}},
}


def _layout(*schemas):
    return PresentationLayoutModel(
        name="t",
        slides=[SlideLayoutModel(id=f"l{index}", json_schema=schema) for index, schema in enumerate(schemas)],
    )


def test_layout_image_slots_counts_placeholders():
    assert slide_photos.layout_image_slots(IMAGE_LAYOUT) == 1
    assert slide_photos.layout_image_slots(TWO_IMAGE_LAYOUT) == 2
    assert slide_photos.layout_image_slots(TEXT_LAYOUT) == 0
    assert slide_photos.layout_image_slots(LEGACY_IMAGE_LAYOUT) == 1


def test_normalize_photos_keeps_own_images_once():
    photos = slide_photos.normalize_photos(
        [
            {"url": "/app_data/images/a.png", "name": "  море   и  горы ", "slide": 2},
            {"url": "/app_data/images/a.png", "slide": 0},
            {"url": "data:image/png;base64,AAAA"},
            {"url": "/app_data/images/b.jpg", "slide": -1},
            {"url": "/app_data/images/c.jpg", "slide": True},
            "junk",
        ],
        check_files=False,
    )
    assert photos == [
        {"url": "/app_data/images/a.png", "name": "море и горы", "slide": 2},
        {"url": "/app_data/images/b.jpg", "name": "b.jpg", "slide": None},
        {"url": "/app_data/images/c.jpg", "name": "c.jpg", "slide": None},
    ]


def test_photos_by_slide_and_toc_alignment():
    record = slide_photos.build_record(
        [
            {"url": "a", "name": "a", "slide": 1},
            {"url": "b", "name": "b", "slide": 1},
            {"url": "c", "name": "c", "slide": 9},
            {"url": "d", "name": "d", "slide": None},
        ],
        "manual",
    )
    per_slide = slide_photos.photos_by_slide(record, 3)
    assert per_slide == [[], ["a", "b"], []]
    # A table of contents after the title slide pushes the photos one slide down.
    assert slide_photos.align_with_inserted_slides(per_slide, insert_at=1, inserted=1) == [[], [], ["a", "b"], []]
    assert slide_photos.align_with_inserted_slides(per_slide, insert_at=1, inserted=0) == per_slide
    assert slide_photos.photos_by_slide(None, 2) == [[], []]


def test_outline_hints_are_a_copy():
    outline = PresentationOutlineModel(slides=[SlideOutlineModel(content="# Море"), SlideOutlineModel(content="# Горы")])
    hinted = slide_photos.outline_with_photo_hints(outline, [[], ["x"]])
    assert slide_photos.PHOTO_HINT in hinted.slides[1].content
    assert slide_photos.PHOTO_HINT not in hinted.slides[0].content
    assert outline.slides[1].content == "# Горы"


def test_ensure_image_layouts_moves_photo_slides_to_image_layouts():
    layout = _layout(TEXT_LAYOUT, IMAGE_LAYOUT, TWO_IMAGE_LAYOUT)
    structure = PresentationStructureModel(slides=[0, 0, 1, 0])
    changed = slide_photos.ensure_image_layouts(structure, layout, [["a"], [], ["b"], ["c", "d"]])
    assert changed == [0, 3]
    assert structure.slides[0] in (1, 2)
    assert structure.slides[1] == 0  # no photo: untouched
    assert structure.slides[2] == 1  # already shows an image
    assert structure.slides[3] == 2  # two photos: the two-image layout


def test_ensure_image_layouts_without_image_layouts_changes_nothing():
    structure = PresentationStructureModel(slides=[0, 0])
    assert slide_photos.ensure_image_layouts(structure, _layout(TEXT_LAYOUT), [["a"], []]) == []
    assert structure.slides == [0, 0]


def test_clean_choices_and_order():
    choices = [
        slide_photos._PhotoChoice(photo=2, slide=1),
        slide_photos._PhotoChoice(photo=1, slide=7),  # no such slide
        slide_photos._PhotoChoice(photo=2, slide=3),  # duplicate answer
        slide_photos._PhotoChoice(photo=9, slide=1),  # no such photo
    ]
    assert slide_photos._clean_choices(choices, 3, 3) == [None, 0, None]
    assert slide_photos.assign_by_order(3, 2) == [0, 1, None]


def _png_file(tmp_path, name, color):
    path = tmp_path / name
    Image.new("RGB", (900, 600), color).save(path)
    return str(path)


def test_match_uses_the_vision_answer(monkeypatch, tmp_path):
    files = {"/app_data/images/sea.png": _png_file(tmp_path, "sea.png", (0, 90, 200))}
    monkeypatch.setattr(slide_photos, "resolve_image_path_to_filesystem", lambda url: files.get(url))
    monkeypatch.setattr(slide_photos, "get_client", lambda config=None: object())
    monkeypatch.setattr(slide_photos, "get_model", lambda: "m")
    monkeypatch.setattr(slide_photos, "get_llm_config", lambda: None)
    seen = {}

    async def fake_generate(client, model, *, messages, **kwargs):
        seen["parts"] = messages[1].content
        return {"photos": [{"photo": 1, "slide": 2, "reason": "море"}]}

    monkeypatch.setattr(slide_photos, "generate_structured_with_schema_retries", fake_generate)
    slides = [SlideOutlineModel(content="# Горы"), SlideOutlineModel(content="# Море")]
    assignment, method = asyncio.run(slide_photos.match_photos_to_slides(["/app_data/images/sea.png"], slides))
    assert (assignment, method) == ([1], "vision")
    image_parts = [part for part in seen["parts"] if isinstance(part, slide_photos.ImageContentPart)]
    assert len(image_parts) == 1
    sent = Image.open(io.BytesIO(image_parts[0].data))
    assert max(sent.size) <= slide_photos.MATCH_IMAGE_SIDE  # downscaled before sending


def test_match_falls_back_to_order_for_text_only_models(monkeypatch, tmp_path):
    files = {
        "/app_data/images/a.png": _png_file(tmp_path, "a.png", (10, 10, 10)),
        "/app_data/images/b.png": _png_file(tmp_path, "b.png", (20, 20, 20)),
    }
    monkeypatch.setattr(slide_photos, "resolve_image_path_to_filesystem", lambda url: files.get(url))
    monkeypatch.setattr(slide_photos, "get_client", lambda config=None: object())
    monkeypatch.setattr(slide_photos, "get_model", lambda: "m")
    monkeypatch.setattr(slide_photos, "get_llm_config", lambda: None)

    async def rejects_images(*args, **kwargs):
        raise RuntimeError("This model does not support image input")

    monkeypatch.setattr(slide_photos, "generate_structured_with_schema_retries", rejects_images)
    slides = [SlideOutlineModel(content="one")]
    assignment, method = asyncio.run(slide_photos.match_photos_to_slides(list(files), slides))
    assert (assignment, method) == ([0, None], "order")


# --- API ------------------------------------------------------------------------


@pytest.fixture
def photos_api(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_DATA_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("DISABLE_AUTH", "true")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'photos.db'}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    presentation_id = uuid.uuid4()

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(User.__table__.create)
            await connection.run_sync(PresentationModel.__table__.create)
            await connection.run_sync(KeyValueSqlModel.__table__.create)
        async with session_maker() as session:
            session.add(
                PresentationModel(
                    id=presentation_id,
                    version=PresentationVersion.V2_STANDARD,
                    content="про путешествия",
                    n_slides=2,
                    language="Russian",
                    outlines={"slides": [{"content": "# Горы"}, {"content": "# Море"}]},
                )
            )
            await session.commit()

    asyncio.run(create())
    images = tmp_path / "images"
    images.mkdir(exist_ok=True)
    Image.new("RGB", (40, 30), (0, 90, 200)).save(images / "sea.png")

    async def override():
        async with session_maker() as session:
            yield session

    app = FastAPI()
    app.add_middleware(LocaleMiddleware)
    app.include_router(outlines_router.OUTLINES_ROUTER)
    app.dependency_overrides[get_async_session] = override
    yield TestClient(app), presentation_id
    asyncio.run(engine.dispose())


def test_api_photos_round_trip_and_match(photos_api, monkeypatch):
    client, presentation_id = photos_api
    base = f"/outlines/{presentation_id}/photos"
    assert client.get(base).json()["photos"] == []

    saved = client.put(
        base,
        json={"photos": [{"url": "/app_data/images/sea.png", "name": "sea.png"}, {"url": "/app_data/images/missing.png"}]},
    )
    assert saved.status_code == 200
    assert [photo["url"] for photo in saved.json()["photos"]] == ["/app_data/images/sea.png"]

    async def fake_match(urls, slides):
        assert [slide.content for slide in slides] == ["# Горы", "# Море"]
        return [1], "vision"

    monkeypatch.setattr(outlines_router, "match_photos_to_slides", fake_match)
    matched = client.post(f"{base}/match", json={}).json()
    assert matched["matched"] == "vision"
    assert matched["photos"][0]["slide"] == 1

    moved = client.put(base, json={"photos": [{"url": "/app_data/images/sea.png", "slide": 0}], "matched": "manual"})
    assert moved.json()["matched"] == "manual"
    assert client.get(base).json()["photos"][0]["slide"] == 0


def test_api_photos_validation(photos_api):
    client, presentation_id = photos_api
    assert client.get(f"/outlines/{uuid.uuid4()}/photos").status_code == 404
    bad_slide = client.put(f"/outlines/{presentation_id}/photos", json={"photos": [{"url": "/app_data/images/sea.png", "slide": -2}]})
    assert bad_slide.status_code == 422
    too_many = client.put(
        f"/outlines/{presentation_id}/photos",
        json={"photos": [{"url": f"/app_data/images/{index}.png"} for index in range(slide_photos.MAX_PHOTOS + 1)]},
    )
    assert too_many.status_code == 422
    empty = client.post(f"/outlines/{presentation_id}/photos/match", json={})
    assert empty.json()["photos"] == []


# --- prepare: photo slides get image layouts, numbering follows the TOC --------


def test_prepare_gives_photo_slides_image_layouts_and_shifts_for_toc(photos_api, monkeypatch, tmp_path):
    from api.v1.ppt.endpoints import presentation as presentation_router

    client, presentation_id = photos_api
    client.put(
        f"/outlines/{presentation_id}/photos",
        json={"photos": [{"url": "/app_data/images/sea.png", "slide": 2}], "matched": "manual"},
    )
    toc_layout = {"type": "object", "properties": {"table_of_contents": {"type": "string"}}}
    layout = PresentationLayoutModel(
        name="t",
        slides=[
            SlideLayoutModel(id="text", json_schema=TEXT_LAYOUT),
            SlideLayoutModel(id="picture", json_schema=IMAGE_LAYOUT),
            SlideLayoutModel(id="toc", name="Table of contents", json_schema=toc_layout),
        ],
    )
    seen = {}

    async def fake_layout(_layout, _session):
        return {"layouts": []}, layout, None

    async def fake_structure(*, presentation_outline, **_kwargs):
        seen["outline"] = [slide.content for slide in presentation_outline.slides]
        return PresentationStructureModel(slides=[0, 0, 0, 0])  # the model ignored the photo

    async def no_memory(*_args, **_kwargs):
        return None

    monkeypatch.setattr(presentation_router, "_resolve_prepare_layout", fake_layout)
    monkeypatch.setattr(presentation_router, "generate_presentation_structure", fake_structure)
    monkeypatch.setattr(presentation_router, "_layout_count", lambda _payload: 3)
    monkeypatch.setattr(presentation_router.MEM0_PRESENTATION_MEMORY_SERVICE, "store_generated_outlines", no_memory)

    app = FastAPI()
    app.add_middleware(LocaleMiddleware)
    app.include_router(presentation_router.PRESENTATION_ROUTER)
    app.dependency_overrides[get_async_session] = client.app.dependency_overrides[get_async_session]
    prepare = TestClient(app)

    # Title slide on, table of contents on (the presentation defaults).
    async def enable_toc():
        async for session in client.app.dependency_overrides[get_async_session]():
            presentation = await session.get(PresentationModel, presentation_id)
            presentation.include_table_of_contents = True
            session.add(presentation)
            await session.commit()

    asyncio.run(enable_toc())
    outlines = [{"content": f"# Слайд {number}"} for number in range(1, 5)]
    response = prepare.post(
        "/presentation/prepare",
        json={"presentation_id": str(presentation_id), "outlines": outlines, "layout": "template:x"},
    )
    assert response.status_code == 200, response.text

    # The layout model was told slide 3 shows an image; the stored outline was not.
    assert slide_photos.PHOTO_HINT in seen["outline"][2]
    assert all(slide_photos.PHOTO_HINT not in content for index, content in enumerate(seen["outline"]) if index != 2)

    record = client.get(f"/outlines/{presentation_id}/photos").json()
    final = record["final"]
    toc_count = len(final) - len(outlines)
    assert toc_count >= 1
    assert final[2 + toc_count] == ["/app_data/images/sea.png"]
    assert sum(1 for photos in final if photos) == 1

    async def stored_structure():
        async for session in client.app.dependency_overrides[get_async_session]():
            presentation = await session.get(PresentationModel, presentation_id)
            return presentation.get_structure().slides

    structure = asyncio.run(stored_structure())
    assert structure[2 + toc_count] == 1  # the photo slide now uses the image layout
    assert structure[1 + toc_count] == 0
