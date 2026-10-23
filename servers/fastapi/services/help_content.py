"""The Help page the administrator edits (Admin → Help).

Nothing stored means the built-in help (the translated texts of the frontend).
Once saved, the edited sections are shown to everyone, whatever the language.
Files live in /app_data/help (signed-in users may open them; mirrored to the
storage like the rest of /app_data).
"""

import logging
import os
import re
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from models.sql.key_value import KeyValueSqlModel
from services.database import async_session_maker
from utils.datetime_utils import get_current_utc_datetime
from utils.get_env import get_app_data_directory_env

LOGGER = logging.getLogger(__name__)

CONTENT_KEY = "help:content"
URL_PREFIX = "/app_data/help/"

MAX_SECTIONS = 50
MAX_TITLE = 200
MAX_BODY = 50_000
MAX_FILES = 20
MAX_VIDEOS = 10
MAX_FILE_NAME = 120
MAX_FILE_BYTES = 50 * 1024 * 1024
FILE_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".txt",
    ".md", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4",
    ".webm", ".mp3",
}

_STORED_NAME = re.compile(r"^[0-9a-f]{32}\.[a-z0-9]{1,5}$")
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
_RUTUBE_ID = re.compile(r"^[0-9a-f]{32}$")
_VK_VIDEO = re.compile(r"video(-?\d+)_(\d+)")


def help_directory() -> str:
    return os.path.join(get_app_data_directory_env() or "/app_data", "help")


def video_embed_url(url: str) -> str | None:
    """A player address for YouTube, Rutube and VK Video links; None for others
    (they are shown as plain links, never put into a frame)."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    parts = [part for part in parsed.path.split("/") if part]
    if host == "youtu.be" and parts:
        video_id = parts[0]
    elif host in ("youtube.com", "youtube-nocookie.com"):
        if parts[:1] == ["watch"]:
            video_id = (parse_qs(parsed.query).get("v") or [""])[0]
        elif len(parts) >= 2 and parts[0] in ("embed", "shorts", "live"):
            video_id = parts[1]
        else:
            video_id = ""
    elif host == "rutube.ru":
        video_id = parts[-1] if len(parts) >= 2 and parts[0] in ("video", "play", "shorts") else ""
        if parts[:2] == ["play", "embed"] and len(parts) >= 3:
            video_id = parts[2]
        return f"https://rutube.ru/play/embed/{video_id}" if _RUTUBE_ID.match(video_id) else None
    elif host in ("vk.com", "vkvideo.ru", "vk.ru"):
        query = parse_qs(parsed.query)
        if parts[:1] == ["video_ext.php"] and query.get("oid") and query.get("id"):
            oid, vid = query["oid"][0], query["id"][0]
        else:
            match = _VK_VIDEO.search(parsed.path + "?" + parsed.query)
            if not match:
                return None
            oid, vid = match.groups()
        if not re.fullmatch(r"-?\d+", oid) or not vid.isdigit():
            return None
        return f"https://vkvideo.ru/video_ext.php?oid={oid}&id={vid}&hd=2"
    else:
        return None
    return f"https://www.youtube-nocookie.com/embed/{video_id}" if _YOUTUBE_ID.match(video_id) else None


def _clean_line(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_file(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None
    url = str(item.get("url") or "")
    stored = url.removeprefix(URL_PREFIX)
    if not url.startswith(URL_PREFIX) or not _STORED_NAME.match(stored):
        return None
    try:
        size = max(0, int(item.get("size") or 0))
    except (TypeError, ValueError):
        size = 0
    return {"name": _clean_line(item.get("name"), MAX_FILE_NAME) or stored, "url": url, "size": size}


def _clean_video(item: Any) -> dict | None:
    url = str((item.get("url") if isinstance(item, dict) else item) or "").strip()[:500]
    if urlparse(url).scheme not in ("http", "https"):
        return None
    title = _clean_line(item.get("title"), MAX_TITLE) if isinstance(item, dict) else ""
    return {"url": url, "title": title, "embed": video_embed_url(url)}


def normalize_sections(raw: Any) -> list[dict]:
    sections = []
    for item in (raw if isinstance(raw, list) else [])[:MAX_SECTIONS]:
        if not isinstance(item, dict):
            continue
        title = _clean_line(item.get("title"), MAX_TITLE)
        body = str(item.get("body") or "").replace("\r\n", "\n").strip()[:MAX_BODY]
        files = [f for f in map(_clean_file, item.get("files") or []) if f][:MAX_FILES]
        videos = [v for v in map(_clean_video, item.get("videos") or []) if v][:MAX_VIDEOS]
        if not (title or body or files or videos):
            continue
        section_id = str(item.get("id") or "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", section_id):
            section_id = uuid.uuid4().hex[:12]
        sections.append(
            {"id": section_id, "title": title, "body": body, "files": files, "videos": videos}
        )
    return sections


async def _read() -> Any:
    try:
        async with async_session_maker() as session:
            row = await session.scalar(
                select(KeyValueSqlModel).where(KeyValueSqlModel.key == CONTENT_KEY)
            )
    except SQLAlchemyError:
        LOGGER.warning("Could not read the help content", exc_info=True)
        return None
    return row.value if row is not None else None


async def _write(value: dict | None) -> None:
    """Store the content; None deletes it (back to the built-in help)."""
    async with async_session_maker() as session:
        if value is None:
            await session.execute(
                delete(KeyValueSqlModel).where(KeyValueSqlModel.key == CONTENT_KEY)
            )
        else:
            row = await session.scalar(
                select(KeyValueSqlModel).where(KeyValueSqlModel.key == CONTENT_KEY)
            )
            if row is None:
                session.add(KeyValueSqlModel(key=CONTENT_KEY, value=value))
            else:
                row.value = value
        await session.commit()


async def load() -> dict | None:
    """The edited help, or None for the built-in one."""
    stored = await _read()
    if not isinstance(stored, dict):
        return None
    return {
        "sections": normalize_sections(stored.get("sections")),
        "updated_at": stored.get("updated_at"),
    }


async def save(raw_sections: Any) -> dict:
    content = {
        "sections": normalize_sections(raw_sections),
        "updated_at": get_current_utc_datetime().isoformat(),
    }
    await _write(content)
    remove_unused_files(content["sections"])
    return content


async def reset() -> None:
    await _write(None)
    remove_unused_files([])


def remove_unused_files(sections: list[dict]) -> int:
    """Delete uploaded files no section uses any more (attached or in the text)."""
    directory = help_directory()
    if not os.path.isdir(directory):
        return 0
    text = " ".join(
        section["body"] + " " + " ".join(file["url"] for file in section["files"])
        for section in sections
    )
    removed = 0
    for name in os.listdir(directory):
        if _STORED_NAME.match(name) and f"{URL_PREFIX}{name}" not in text:
            try:
                os.remove(os.path.join(directory, name))
                removed += 1
            except OSError:
                LOGGER.warning("Could not delete the help file %s", name, exc_info=True)
    return removed


def stored_file_name(original_name: str) -> str | None:
    """A new random name with the original extension, or None for a file type
    the help does not take."""
    extension = os.path.splitext(original_name or "")[1].lower()
    if extension not in FILE_EXTENSIONS:
        return None
    return f"{uuid.uuid4().hex}{extension}"
