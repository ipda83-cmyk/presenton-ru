from utils.i18n import (
    LOCALE_HEADER,
    reset_current_locale,
    resolve_locale,
    set_current_locale,
)

_LOCALE_HEADER = LOCALE_HEADER.encode("latin-1")
_ACCEPT_LANGUAGE = b"accept-language"
_CONTENT_LANGUAGE = b"content-language"


class LocaleMiddleware:
    """Resolves the UI locale once per request and exposes it to ``t()``.

    Plain ASGI (not BaseHTTPMiddleware) so streaming/SSE responses pass through
    untouched. Must wrap SessionAuthMiddleware so its error bodies are
    localized too.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        header_locale = None
        accept_language = None
        cookie_parts: list[str] = []
        for name, value in scope.get("headers") or ():
            if name == _LOCALE_HEADER:
                header_locale = value.decode("latin-1")
            elif name == _ACCEPT_LANGUAGE:
                accept_language = value.decode("latin-1")
            elif name == b"cookie":
                # HTTP/2 clients may split cookies across several headers.
                cookie_parts.append(value.decode("latin-1"))
        locale = resolve_locale(
            header_locale, "; ".join(cookie_parts) or None, accept_language
        )

        async def send_with_language(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or ())
                if not any(key.lower() == _CONTENT_LANGUAGE for key, _ in headers):
                    headers.append((_CONTENT_LANGUAGE, locale.encode("latin-1")))
                    message = {**message, "headers": headers}
            await send(message)

        token = set_current_locale(locale)
        try:
            await self.app(
                scope,
                receive,
                send_with_language if scope["type"] == "http" else send,
            )
        finally:
            reset_current_locale(token)
