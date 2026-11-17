"""The offer and the personal data policy: read by anyone, edited by administrators.

GET /api/v1/legal/{doc} is public (see _PUBLIC_AUTH_PREFIXES in
api/middlewares.py); the /api/v1/admin/ prefix is for administrators.
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services import legal
from utils.i18n import http_error

API_V1_LEGAL_ROUTER = APIRouter(prefix="/api/v1/legal", tags=["Legal"])
API_V1_ADMIN_LEGAL_ROUTER = APIRouter(prefix="/api/v1/admin/legal", tags=["Legal"])


class LegalDocument(BaseModel):
    title: str = Field(default="", max_length=legal.MAX_TITLE)
    body: str = Field(default="", max_length=legal.MAX_BODY)


def _known(doc: str) -> str:
    if doc not in legal.DOCUMENTS:
        raise http_error(404, "auth.documentNotFound")
    return doc


@API_V1_LEGAL_ROUTER.get("/{doc}")
async def read_document(doc: str):
    return await legal.load(_known(doc))


@API_V1_ADMIN_LEGAL_ROUTER.put("/{doc}")
async def save_document(doc: str, body: LegalDocument):
    return await legal.save(_known(doc), body.title, body.body)
