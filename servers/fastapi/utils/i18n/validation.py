from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from utils.i18n import en as _en
from utils.i18n import format_message, get_current_locale
from utils.i18n import ru as _ru

# pydantic error ``type`` -> template; the ``ctx`` pydantic attaches fills the
# placeholders. Locales without an entry keep pydantic's own English ``msg``.
_VALIDATION_CATALOGS: dict[str, dict[str, str]] = {
    "ru": _ru.VALIDATION_MESSAGES,
    "en": _en.VALIDATION_MESSAGES,
}


def localize_validation_errors(errors: list[dict], locale: str) -> list[dict]:
    catalog = _VALIDATION_CATALOGS.get(locale) or {}
    localized = []
    for error in errors:
        item = dict(error)
        template = catalog.get(str(item.get("type") or ""))
        if template:
            ctx = item.get("ctx")
            item["msg"] = format_message(template, ctx if isinstance(ctx, dict) else {})
        localized.append(item)
    return localized


async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Same shape as FastAPI's default handler; only ``msg`` is localized.
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(
                localize_validation_errors(list(exc.errors()), get_current_locale())
            )
        },
    )
