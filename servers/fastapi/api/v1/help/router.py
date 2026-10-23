"""Help page: everyone reads it, administrators edit it (Admin → Help).

The /api/v1/admin/ prefix is guarded by the session middleware.
"""

import os

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel, Field

from services import help_content
from utils.i18n import http_error

API_V1_HELP_ROUTER = APIRouter(prefix="/api/v1/help", tags=["Help"])
API_V1_ADMIN_HELP_ROUTER = APIRouter(prefix="/api/v1/admin/help", tags=["Help"])

UPLOAD_CHUNK = 1024 * 1024


class HelpContent(BaseModel):
    sections: list[dict] = Field(default_factory=list, max_length=help_content.MAX_SECTIONS)


def _answer(content: dict | None) -> dict:
    if content is None:
        return {"custom": False, "sections": [], "updated_at": None}
    return {"custom": True, **content}


@API_V1_HELP_ROUTER.get("")
async def read_help():
    return _answer(await help_content.load())


@API_V1_ADMIN_HELP_ROUTER.put("")
async def save_help(body: HelpContent):
    return _answer(await help_content.save(body.sections))


@API_V1_ADMIN_HELP_ROUTER.delete("")
async def reset_help():
    """Back to the built-in help."""
    await help_content.reset()
    return _answer(None)


@API_V1_ADMIN_HELP_ROUTER.post("/files")
async def upload_help_file(file: UploadFile = File(...)):
    stored = help_content.stored_file_name(file.filename or "")
    if stored is None:
        raise http_error(
            400,
            "err.help.fileType",
            types=", ".join(sorted(help_content.FILE_EXTENSIONS)),
        )
    directory = help_content.help_directory()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, stored)
    size = 0
    try:
        with open(path, "wb") as handle:
            while chunk := await file.read(UPLOAD_CHUNK):
                size += len(chunk)
                if size > help_content.MAX_FILE_BYTES:
                    raise http_error(
                        413, "err.help.fileTooLarge", mb=help_content.MAX_FILE_BYTES // (1024 * 1024)
                    )
                handle.write(chunk)
    except BaseException:
        if os.path.exists(path):
            os.remove(path)
        raise
    if size == 0:
        os.remove(path)
        raise http_error(400, "err.help.fileEmpty")
    name = " ".join((file.filename or stored).split())[: help_content.MAX_FILE_NAME]
    return {"name": name, "url": f"{help_content.URL_PREFIX}{stored}", "size": size}
