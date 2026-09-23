import asyncio
import re
import string

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

import utils.provider_error_messages as provider_messages
from utils.i18n import (
    DEFAULT_LOCALE,
    SOURCE_LOCALE,
    cookie_value,
    en,
    negotiate_locale,
    normalize_preference,
    get_current_locale,
    http_error,
    normalize_locale,
    reset_current_locale,
    resolve_locale,
    ru,
    set_current_locale,
    t,
    translate,
)
from utils.i18n.middleware import LocaleMiddleware
from utils.i18n.validation import (
    localize_validation_errors,
    request_validation_exception_handler,
)


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


# --- catalogs -----------------------------------------------------------------


def test_catalogs_have_identical_keys():
    assert set(ru.MESSAGES) == set(en.MESSAGES)


@pytest.mark.parametrize("key", sorted(en.MESSAGES))
def test_catalog_placeholders_match(key):
    assert _placeholders(ru.MESSAGES[key]) == _placeholders(en.MESSAGES[key])


def test_catalogs_contain_no_stray_braces():
    # Only simple {name} placeholders are allowed; anything else would be
    # returned unformatted by format_message().
    for catalog in (ru.MESSAGES, en.MESSAGES, ru.VALIDATION_MESSAGES):
        for key, template in catalog.items():
            stripped = re.sub(r"\{[A-Za-z_][A-Za-z0-9_]*\}", "", template)
            assert "{" not in stripped and "}" not in stripped, key


def test_provider_constants_match_english_catalog():
    assert provider_messages.INVALID_API_KEY_MESSAGE == en.MESSAGES["provider.invalidApiKey"]
    assert provider_messages.IMAGE_MODERATION_MESSAGE == en.MESSAGES["provider.imageModeration"]
    assert provider_messages.GENERIC_PROVIDER_ERROR_MESSAGE == en.MESSAGES["provider.generic"]


# --- locale resolution --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ru", "ru"),
        ("EN", "en"),
        ("  en  ", "en"),
        ("en-US", "en"),
        ("ru_RU", "ru"),
        ("fr", None),
        ("", None),
        (None, None),
        ("-", None),
        ("ru" * 5000, None),
    ],
)
def test_normalize_locale(raw, expected):
    assert normalize_locale(raw) == expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("NEXT_LOCALE=en", "en"),
        ("a=1; NEXT_LOCALE=en; b=2", "en"),
        ('NEXT_LOCALE="en"', "en"),
        ("XNEXT_LOCALE=en", None),
        ("NEXT_LOCALE", None),
        ("NEXT_LOCALE=", ""),
        ("garbage;;=;NEXT_LOCALE=en", "en"),
        ('bad="unterminated; NEXT_LOCALE=en', "en"),
        ("", None),
        (None, None),
    ],
)
def test_cookie_value(header, expected):
    assert cookie_value(header, "NEXT_LOCALE") == expected


def test_resolve_locale_precedence():
    assert resolve_locale(None, None) == DEFAULT_LOCALE == "ru"
    assert resolve_locale(None, "NEXT_LOCALE=en") == "en"
    assert resolve_locale("en", "NEXT_LOCALE=ru") == "en"
    assert resolve_locale("ru", "NEXT_LOCALE=en") == "ru"
    # Unsupported header falls through to the cookie, then to the default.
    assert resolve_locale("fr", "NEXT_LOCALE=en") == "en"
    assert resolve_locale("fr", "NEXT_LOCALE=de") == "ru"


# Same cases as negotiateLocale in servers/nextjs/tests (i18n-config.test.mjs).
@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("en-US,en;q=0.9", "en"),
        ("ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7", "ru"),
        ("de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7", "en"),
        ("de,fr", None),
        ("en;q=0.5, ru;q=0.8", "ru"),
        ("ru;q=0, en", "en"),
        ("en;q=abc, ru", "ru"),
        ("*", None),
        ("  EN-gb ", "en"),
        ("", None),
        (None, None),
    ],
)
def test_negotiate_locale(header, expected):
    assert negotiate_locale(header) == expected


def test_normalize_preference():
    assert normalize_preference("auto") == "auto"
    assert normalize_preference(" AUTO ") == "auto"
    assert normalize_preference("en-US") == "en"
    assert normalize_preference("automatic") is None
    assert normalize_preference(None) is None


def test_resolve_locale_auto_follows_the_browser_only_when_asked():
    english_browser = "en-US,en;q=0.9"
    assert resolve_locale(None, "NEXT_LOCALE=auto", english_browser) == "en"
    assert resolve_locale(None, "NEXT_LOCALE=auto", "ru-RU,ru") == "ru"
    # Unsupported or missing browser language -> default.
    assert resolve_locale(None, "NEXT_LOCALE=auto", "de") == "ru"
    assert resolve_locale(None, "NEXT_LOCALE=auto", None) == "ru"
    # An explicit choice (or no choice) is never overridden by the browser.
    assert resolve_locale(None, "NEXT_LOCALE=ru", english_browser) == "ru"
    assert resolve_locale(None, None, english_browser) == "ru"
    # The explicit header still wins over "auto".
    assert resolve_locale("ru", "NEXT_LOCALE=auto", english_browser) == "ru"


# --- translation --------------------------------------------------------------


def test_default_locale_outside_request_is_source_language():
    assert get_current_locale() == SOURCE_LOCALE == "en"
    assert t("auth.unauthorized") == "Unauthorized"


def test_t_follows_context_locale():
    token = set_current_locale("ru")
    try:
        assert t("auth.unauthorized") == ru.MESSAGES["auth.unauthorized"]
    finally:
        reset_current_locale(token)
    assert t("auth.unauthorized") == "Unauthorized"


def test_set_current_locale_rejects_unknown_values():
    token = set_current_locale("de")
    try:
        assert get_current_locale() == DEFAULT_LOCALE
    finally:
        reset_current_locale(token)


def test_translate_formats_and_never_raises():
    assert translate("ru", "auth.usernameTooShort", min=3).startswith("Имя пользователя")
    assert "3" in translate("ru", "auth.usernameTooShort", min=3)
    # Missing params stay literal instead of raising KeyError.
    assert "{min}" in translate("en", "auth.usernameTooShort")
    assert "{min}" in translate("en", "auth.usernameTooShort", other=1)
    # Unknown keys come back as the key (and are logged), not an exception.
    assert translate("ru", "no.such.key") == "no.such.key"
    # Unknown locale falls back to the source catalog.
    assert translate("de", "auth.unauthorized") == "Unauthorized"


def test_http_error_carries_localized_detail():
    token = set_current_locale("ru")
    try:
        error = http_error(404, "admin.userNotFound", headers={"X-Test": "1"})
    finally:
        reset_current_locale(token)
    assert isinstance(error, HTTPException)
    assert error.status_code == 404
    assert error.detail == ru.MESSAGES["admin.userNotFound"]
    assert error.headers == {"X-Test": "1"}


def test_provider_messages_follow_locale():
    assert (
        provider_messages.safe_provider_error_detail(
            "OpenAI", "image generation", code="insufficient_quota"
        )
        == "OpenAI image generation failed because API quota is unavailable. "
        "Check OpenAI API billing and the limits for the project that owns this API key."
    )
    token = set_current_locale("ru")
    try:
        quota = provider_messages.safe_provider_error_detail(
            "OpenAI", "image generation", code="insufficient_quota"
        )
        generic = provider_messages.safe_llm_provider_error_detail(message="")
        prefixed = provider_messages.safe_provider_error_detail("", "", status_code=500)
    finally:
        reset_current_locale(token)
    assert quota.startswith("OpenAI (генерация изображения): ")
    assert "квота API" in quota
    assert generic == ru.MESSAGES["provider.generic"]
    assert prefixed.startswith("ИИ-провайдер (запрос)")


# --- middleware ---------------------------------------------------------------


def _locale_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)

    class Body(BaseModel):
        password: str = Field(min_length=8)

    @app.get("/who")
    async def who():
        return {"locale": get_current_locale(), "msg": t("auth.unauthorized")}

    @app.get("/fail")
    async def fail():
        raise http_error(401, "auth.unauthorized")

    @app.post("/validate")
    async def validate(body: Body):
        return {"ok": True}

    @app.get("/stream")
    async def stream():
        async def chunks():
            for _ in range(3):
                await asyncio.sleep(0)
                yield (get_current_locale() + "\n").encode()

        return StreamingResponse(chunks(), media_type="text/plain")

    @app.get("/slow")
    async def slow():
        await asyncio.sleep(0.05)
        return {"locale": get_current_locale()}

    app.add_middleware(LocaleMiddleware)
    return app


@pytest.fixture
def client():
    return TestClient(_locale_app())


def test_middleware_defaults_to_russian(client):
    response = client.get("/who")
    assert response.json() == {"locale": "ru", "msg": ru.MESSAGES["auth.unauthorized"]}
    assert response.headers["content-language"] == "ru"


def test_middleware_reads_cookie_and_header(client):
    assert client.get("/who", headers={"Cookie": "NEXT_LOCALE=en"}).json()["locale"] == "en"
    assert (
        client.get("/who", headers={"X-Locale": "en", "Cookie": "NEXT_LOCALE=ru"})
        .json()["locale"]
        == "en"
    )
    assert client.get("/who", headers={"Cookie": "NEXT_LOCALE=klingon"}).json()["locale"] == "ru"


def test_middleware_auto_uses_accept_language(client):
    english = {"Cookie": "NEXT_LOCALE=auto", "Accept-Language": "en-US,en;q=0.9"}
    response = client.get("/who", headers=english)
    assert response.json() == {"locale": "en", "msg": "Unauthorized"}
    assert response.headers["content-language"] == "en"
    assert (
        client.get("/who", headers={"Accept-Language": "en-US"}).json()["locale"] == "ru"
    )


def test_middleware_joins_split_cookie_headers():
    app = _locale_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            request = http.build_request(
                "GET", "/who", headers=[("cookie", "a=1"), ("cookie", "NEXT_LOCALE=en")]
            )
            return await http.send(request)

    assert asyncio.run(run()).json()["locale"] == "en"


def test_middleware_localizes_http_errors(client):
    assert client.get("/fail").json() == {"detail": ru.MESSAGES["auth.unauthorized"]}
    assert client.get("/fail", headers={"Cookie": "NEXT_LOCALE=en"}).json() == {
        "detail": "Unauthorized"
    }


def test_middleware_resets_locale_after_request(client):
    client.get("/who", headers={"Cookie": "NEXT_LOCALE=ru"})
    assert get_current_locale() == SOURCE_LOCALE


def test_streaming_responses_keep_locale(client):
    body = client.get("/stream", headers={"Cookie": "NEXT_LOCALE=en"}).text
    assert body.splitlines() == ["en", "en", "en"]


def test_concurrent_requests_do_not_share_locale():
    app = _locale_app()

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            return await asyncio.gather(
                *[
                    http.get("/slow", headers={"X-Locale": locale})
                    for locale in ("ru", "en") * 10
                ]
            )

    responses = asyncio.run(run())
    assert [r.json()["locale"] for r in responses] == ["ru", "en"] * 10


def test_non_http_scopes_pass_through():
    seen = {}

    async def inner(scope, receive, send):
        seen["type"] = scope["type"]

    asyncio.run(LocaleMiddleware(inner)({"type": "lifespan"}, None, None))
    assert seen == {"type": "lifespan"}


# --- request validation (422) -------------------------------------------------


def test_validation_errors_localized_in_russian(client):
    response = client.post("/validate", json={"password": "short"})
    assert response.status_code == 422
    [error] = response.json()["detail"]
    assert error["loc"] == ["body", "password"]
    assert error["type"] == "string_too_short"
    assert error["msg"] == "Должно быть не короче 8 симв."


def test_validation_errors_keep_pydantic_english(client):
    response = client.post(
        "/validate", json={"password": "short"}, headers={"Cookie": "NEXT_LOCALE=en"}
    )
    assert response.json()["detail"][0]["msg"] == "String should have at least 8 characters"


def test_validation_missing_and_malformed_bodies(client):
    missing = client.post("/validate", json={})
    assert missing.json()["detail"][0]["msg"] == ru.VALIDATION_MESSAGES["missing"]
    broken = client.post(
        "/validate", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert broken.status_code == 422
    assert broken.json()["detail"][0]["msg"] == ru.VALIDATION_MESSAGES["json_invalid"]


def test_unknown_validation_types_keep_original_message():
    errors = [{"type": "brand_new_type", "loc": ("body",), "msg": "Original"}]
    assert localize_validation_errors(errors, "ru")[0]["msg"] == "Original"
    # ctx that is not a dict (or missing) must not break formatting.
    weird = [{"type": "string_too_short", "loc": ("body",), "msg": "x", "ctx": "nope"}]
    assert "{min_length}" in localize_validation_errors(weird, "ru")[0]["msg"]


def _backend_translation_keys():
    """Every literal key passed to t(...) / http_error(status, ...) in app code."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    call = re.compile(
        r"""(?<![\w.])(?:t\(\s*|http_error\(\s*[^,()]+,\s*)["']([A-Za-z][\w.]*)["']"""
    )
    found = {}
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(("tests/", ".venv/", "alembic/")):
            continue
        for match in call.finditer(path.read_text(encoding="utf-8")):
            found.setdefault(match.group(1), rel)
    return found


def test_every_backend_translation_key_exists_in_both_catalogs():
    keys = _backend_translation_keys()
    # The migration touched dozens of modules; make sure the scan sees them.
    assert len(keys) > 200
    missing = {
        key: where
        for key, where in keys.items()
        if key not in en.MESSAGES or key not in ru.MESSAGES
    }
    assert missing == {}


def test_migrated_http_errors_follow_request_locale(client):
    app = FastAPI()
    app.add_middleware(LocaleMiddleware)

    @app.get("/missing")
    async def missing():
        raise HTTPException(
            status_code=404, detail=t("err.presentation.presentationNotFound")
        )

    local = TestClient(app)
    assert local.get("/missing").json()["detail"] == "Презентация не найдена"
    assert (
        local.get("/missing", headers={"X-Locale": "en"}).json()["detail"]
        == "Presentation not found"
    )
