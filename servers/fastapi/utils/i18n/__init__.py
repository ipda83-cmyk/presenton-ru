"""User-facing backend messages in the UI locale (RU default, EN switchable).

Locale resolution for HTTP requests mirrors the frontend
(servers/nextjs/i18n/request.ts): ``X-Locale`` header -> ``NEXT_LOCALE``
cookie -> Russian. Accept-Language is ignored on purpose: the frontend ignores
it too, so honouring it here would show English errors inside a Russian UI.

Outside a request (startup jobs, CLI, tests) messages stay in the English
source language, so code paths that never see a user keep their old output.

Catalogs are Python modules rather than JSON so the PyInstaller (Electron)
build bundles them through normal imports.
"""

import logging
from collections.abc import Mapping
from contextvars import ContextVar, Token

from fastapi import HTTPException

from utils.i18n import en as _en
from utils.i18n import ru as _ru

SUPPORTED_LOCALES = ("ru", "en")
DEFAULT_LOCALE = "ru"
SOURCE_LOCALE = "en"
LOCALE_COOKIE = "NEXT_LOCALE"
LOCALE_HEADER = "x-locale"

_CATALOGS: dict[str, dict[str, str]] = {"ru": _ru.MESSAGES, "en": _en.MESSAGES}
_FALLBACK_ORDER = (SOURCE_LOCALE, DEFAULT_LOCALE)

_CURRENT_LOCALE: ContextVar[str] = ContextVar(
    "presenton_current_locale", default=SOURCE_LOCALE
)

_logger = logging.getLogger(__name__)


def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    primary = value.strip().lower().replace("_", "-").split("-", 1)[0]
    return primary if primary in SUPPORTED_LOCALES else None


def cookie_value(cookie_header: str | None, name: str) -> str | None:
    # Parsed by hand: http.cookies.SimpleCookie drops the whole header when any
    # unrelated cookie is malformed, which would silently reset the locale.
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        key, sep, value = part.strip().partition("=")
        if sep and key.strip() == name:
            return value.strip().strip('"')
    return None


def resolve_locale(header_value: str | None, cookie_header: str | None) -> str:
    return (
        normalize_locale(header_value)
        or normalize_locale(cookie_value(cookie_header, LOCALE_COOKIE))
        or DEFAULT_LOCALE
    )


def get_current_locale() -> str:
    return _CURRENT_LOCALE.get()


def set_current_locale(locale: str) -> Token:
    return _CURRENT_LOCALE.set(normalize_locale(locale) or DEFAULT_LOCALE)


def reset_current_locale(token: Token) -> None:
    _CURRENT_LOCALE.reset(token)


class _KeepMissing(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def format_message(template: str, params: Mapping[str, object]) -> str:
    """Fills ``{name}`` placeholders; unknown ones stay literal. Never raises."""
    if not params:
        return template
    try:
        return template.format_map(_KeepMissing(params))
    except (ValueError, IndexError, AttributeError, KeyError, TypeError):
        _logger.warning("Could not format backend message: %r", template)
        return template


def translate(locale: str, key: str, /, **params: object) -> str:
    """Never raises: a translation problem must not turn a 4xx into a 500."""
    template = _CATALOGS.get(locale, {}).get(key)
    if template is None:
        for fallback in _FALLBACK_ORDER:
            template = _CATALOGS[fallback].get(key)
            if template is not None:
                break
    if template is None:
        _logger.warning("Missing backend i18n key: %s", key)
        return key
    return format_message(template, params)


def t(key: str, /, **params: object) -> str:
    return translate(get_current_locale(), key, **params)


def http_error(
    status_code: int,
    key: str,
    /,
    *,
    headers: dict[str, str] | None = None,
    **params: object,
) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail=t(key, **params), headers=headers
    )
