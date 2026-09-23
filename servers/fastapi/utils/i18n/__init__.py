"""User-facing backend messages in the UI locale (RU default, EN switchable).

Locale resolution for HTTP requests mirrors the frontend
(servers/nextjs/i18n/request.ts): ``X-Locale`` header -> ``NEXT_LOCALE``
cookie -> Russian. The cookie holds the user's *preference*: ``ru``, ``en`` or
``auto``. Accept-Language is consulted only for ``auto`` (with the same
negotiation as the frontend), so an explicit choice is never overridden by the
browser and the errors always match the language of the UI.

Outside a request (startup jobs, CLI, tests) messages stay in the English
source language, so code paths that never see a user keep their old output.

Catalogs are Python modules rather than JSON so the PyInstaller (Electron)
build bundles them through normal imports.
"""

import logging
import re
from collections.abc import Mapping
from contextvars import ContextVar, Token

from fastapi import HTTPException

from utils.i18n import en as _en
from utils.i18n import ru as _ru

SUPPORTED_LOCALES = ("ru", "en")
AUTO_LOCALE = "auto"
LOCALE_PREFERENCES = (*SUPPORTED_LOCALES, AUTO_LOCALE)
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


def normalize_preference(value: str | None) -> str | None:
    """``ru``/``en``/``auto`` as stored in the cookie and the user profile."""
    if value and value.strip().lower() == AUTO_LOCALE:
        return AUTO_LOCALE
    return normalize_locale(value)


_QUALITY = re.compile(r"0(\.\d{0,3})?|1(\.0{0,3})?")


def negotiate_locale(accept_language: str | None) -> str | None:
    """First supported language of an Accept-Language header, by q-value.

    Keep in sync with ``negotiateLocale`` in servers/nextjs/i18n/config.ts.
    """
    if not accept_language:
        return None
    ranked: list[tuple[float, int, str]] = []
    for index, part in enumerate(accept_language.split(",")):
        tag, *params = [item.strip() for item in part.split(";")]
        quality = 1.0
        for param in params:
            name, _, value = param.partition("=")
            if name.strip().lower() == "q":
                value = value.strip()
                quality = float(value) if _QUALITY.fullmatch(value) else 0.0
        if tag and quality > 0:
            ranked.append((-quality, index, tag))
    for _, _, tag in sorted(ranked):
        locale = normalize_locale(tag)
        if locale:
            return locale
    return None


def resolve_locale(
    header_value: str | None,
    cookie_header: str | None,
    accept_language: str | None = None,
) -> str:
    header_locale = normalize_locale(header_value)
    if header_locale:
        return header_locale
    preference = normalize_preference(cookie_value(cookie_header, LOCALE_COOKIE))
    if preference == AUTO_LOCALE:
        return negotiate_locale(accept_language) or DEFAULT_LOCALE
    return preference or DEFAULT_LOCALE


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
