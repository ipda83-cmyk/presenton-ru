import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.help import router as help_router
from services import help_content
from utils.i18n.middleware import LocaleMiddleware


@pytest.fixture()
def stored(monkeypatch, tmp_path):
    """The help in memory and its files in a temporary /app_data."""
    box: dict = {"value": None}

    async def read():
        return box["value"]

    async def write(value):
        box["value"] = value

    monkeypatch.setattr(help_content, "_read", read)
    monkeypatch.setattr(help_content, "_write", write)
    monkeypatch.setenv("APP_DATA_DIRECTORY", str(tmp_path))
    return box


def _client():
    app = FastAPI()
    app.add_middleware(LocaleMiddleware)
    app.include_router(help_router.API_V1_HELP_ROUTER)
    app.include_router(help_router.API_V1_ADMIN_HELP_ROUTER)
    return TestClient(app)


@pytest.mark.parametrize(
    "url, embed",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"),
        (
            "https://rutube.ru/video/0123456789abcdef0123456789abcdef/",
            "https://rutube.ru/play/embed/0123456789abcdef0123456789abcdef",
        ),
        ("https://vk.com/video-12345_678", "https://vkvideo.ru/video_ext.php?oid=-12345&id=678&hd=2"),
        ("https://vkvideo.ru/video-12345_678", "https://vkvideo.ru/video_ext.php?oid=-12345&id=678&hd=2"),
        ("https://vimeo.com/123", None),
        ("javascript:alert(1)", None),
        ("https://www.youtube.com/watch?v=<script>", None),
    ],
)
def test_video_links_become_players_only_for_known_sites(url, embed):
    assert help_content.video_embed_url(url) == embed


def test_sections_are_cleaned_up():
    sections = help_content.normalize_sections(
        [
            {
                "id": "start",
                "title": "  Как   начать ",
                "body": "Текст\r\n**жирный**",
                "files": [
                    {"name": "Инструкция.pdf", "url": "/app_data/help/" + "a" * 32 + ".pdf", "size": 10},
                    {"name": "чужой", "url": "/app_data/images/x.png"},
                    {"name": "выход", "url": "/app_data/help/../../etc/passwd"},
                ],
                "videos": ["https://youtu.be/dQw4w9WgXcQ", {"url": "ftp://x"}, {"url": "https://vimeo.com/1", "title": "Обзор"}],
            },
            {"title": "", "body": "  ", "files": [], "videos": []},
            "мусор",
            {"id": "bad id!", "title": "Второй"},
        ]
    )
    assert [section["title"] for section in sections] == ["Как начать", "Второй"]
    first = sections[0]
    assert first["id"] == "start" and first["body"] == "Текст\n**жирный**"
    assert [file["name"] for file in first["files"]] == ["Инструкция.pdf"]
    assert first["videos"] == [
        {"url": "https://youtu.be/dQw4w9WgXcQ", "title": "", "embed": "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"},
        {"url": "https://vimeo.com/1", "title": "Обзор", "embed": None},
    ]
    assert sections[1]["id"] != "bad id!" and len(sections[1]["id"]) == 12


def test_everyone_reads_the_builtin_help_until_an_administrator_saves(stored):
    client = _client()
    assert client.get("/api/v1/help").json() == {"custom": False, "sections": [], "updated_at": None}

    state = client.put(
        "/api/v1/admin/help", json={"sections": [{"id": "a", "title": "Раздел", "body": "Текст"}]}
    ).json()
    assert state["custom"] is True and state["updated_at"]
    assert client.get("/api/v1/help").json()["sections"] == [
        {"id": "a", "title": "Раздел", "body": "Текст", "files": [], "videos": []}
    ]

    assert client.delete("/api/v1/admin/help").json()["custom"] is False
    assert stored["value"] is None


def test_files_are_uploaded_and_removed_when_no_section_uses_them(stored, tmp_path):
    client = _client()
    response = client.post(
        "/api/v1/admin/help/files", files={"file": ("Инструкция.pdf", b"%PDF-1.4 test", "application/pdf")}
    )
    assert response.status_code == 200, response.text
    pdf = response.json()
    assert pdf["name"] == "Инструкция.pdf" and pdf["size"] == 13
    assert pdf["url"].startswith("/app_data/help/") and pdf["url"].endswith(".pdf")
    picture = client.post(
        "/api/v1/admin/help/files", files={"file": ("схема.png", b"\x89PNG data", "image/png")}
    ).json()
    folder = tmp_path / "help"
    assert len(os.listdir(folder)) == 2

    # The picture is used in the text, the PDF is attached.
    body = {"sections": [{"title": "Файлы", "body": f"![схема]({picture['url']})", "files": [pdf]}]}
    client.put("/api/v1/admin/help", json=body)
    assert len(os.listdir(folder)) == 2

    body["sections"][0]["files"] = []
    client.put("/api/v1/admin/help", json=body)
    assert os.listdir(folder) == [picture["url"].rsplit("/", 1)[1]]

    client.delete("/api/v1/admin/help")
    assert os.listdir(folder) == []


def test_unsafe_or_empty_files_are_refused(stored, tmp_path, monkeypatch):
    client = _client()
    for name in ("page.html", "script.js", "drawing.svg", "noextension"):
        response = client.post("/api/v1/admin/help/files", files={"file": (name, b"x", "text/plain")})
        assert response.status_code == 400, name
    assert client.post("/api/v1/admin/help/files", files={"file": ("a.pdf", b"", "application/pdf")}).status_code == 400
    monkeypatch.setattr(help_content, "MAX_FILE_BYTES", 4)
    response = client.post("/api/v1/admin/help/files", files={"file": ("a.pdf", b"12345", "application/pdf")})
    assert response.status_code == 413
    assert not (tmp_path / "help").exists() or os.listdir(tmp_path / "help") == []
