import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.v1.auth.config import SESSION_COOKIE_NAME
from api.v1.auth.router import API_V1_AUTH_ROUTER
from models.sql.api_key import ApiKey
from models.sql.key_value import KeyValueSqlModel
from models.sql.user import User
from services.database import get_async_session
from utils.i18n.middleware import LocaleMiddleware


def _build_client(tmp_path, *, with_key_value: bool = True):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'locale.db'}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def create_tables():
        async with engine.begin() as connection:
            await connection.run_sync(User.__table__.create)
            await connection.run_sync(ApiKey.__table__.create)
            if with_key_value:
                await connection.run_sync(KeyValueSqlModel.__table__.create)

    asyncio.run(create_tables())

    async def override_session():
        async with session_maker() as session:
            yield session

    app = FastAPI()
    app.add_middleware(LocaleMiddleware)
    app.include_router(API_V1_AUTH_ROUTER)
    app.dependency_overrides[get_async_session] = override_session
    return TestClient(app), engine


def _setup_admin(client):
    response = client.post(
        "/api/v1/auth/setup",
        json={"username": "admin", "password": "secret123"},
    )
    assert response.status_code == 200


def _login(client, locale_cookie=None):
    headers = {"Cookie": f"NEXT_LOCALE={locale_cookie}"} if locale_cookie else {}
    return client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "secret123"},
        headers=headers,
    )


def test_first_login_remembers_the_language_in_use(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_CONFIG_PATH", str(tmp_path / "userConfig.json"))
    monkeypatch.delenv("DISABLE_AUTH", raising=False)
    client, engine = _build_client(tmp_path)
    _setup_admin(client)

    response = _login(client, "en")

    assert response.status_code == 200
    assert response.cookies.get("NEXT_LOCALE") == "en"
    status = client.get(
        "/api/v1/auth/status",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={response.cookies[SESSION_COOKIE_NAME]}"},
    )
    assert status.json()["locale"] == "en"
    asyncio.run(engine.dispose())


def test_profile_language_wins_over_a_new_browser_cookie(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_CONFIG_PATH", str(tmp_path / "userConfig.json"))
    monkeypatch.delenv("DISABLE_AUTH", raising=False)
    client, engine = _build_client(tmp_path)
    _setup_admin(client)
    session_cookie = _login(client, "ru").cookies[SESSION_COOKIE_NAME]

    switched = client.put(
        "/api/v1/auth/locale",
        json={"locale": "en"},
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={session_cookie}"},
    )
    assert switched.status_code == 200
    assert switched.json() == {"locale": "en", "persisted": True}
    assert switched.cookies.get("NEXT_LOCALE") == "en"

    # Another browser: no language cookie (defaults to Russian) or a stale one.
    client.cookies.clear()
    assert _login(client).cookies.get("NEXT_LOCALE") == "en"
    client.cookies.clear()
    assert _login(client, "ru").cookies.get("NEXT_LOCALE") == "en"
    asyncio.run(engine.dispose())


def test_locale_update_validates_input_and_works_anonymously(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_CONFIG_PATH", str(tmp_path / "userConfig.json"))
    monkeypatch.delenv("DISABLE_AUTH", raising=False)
    client, engine = _build_client(tmp_path)

    for bad in ({"locale": "de"}, {"locale": ""}, {}, {"locale": None}):
        response = client.put("/api/v1/auth/locale", json=bad)
        assert response.status_code == 422

    anonymous = client.put("/api/v1/auth/locale", json={"locale": "ru"})
    assert anonymous.status_code == 200
    assert anonymous.json() == {"locale": "ru", "persisted": False}
    assert anonymous.cookies.get("NEXT_LOCALE") == "ru"
    asyncio.run(engine.dispose())


def test_login_survives_a_missing_language_store(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_CONFIG_PATH", str(tmp_path / "userConfig.json"))
    monkeypatch.delenv("DISABLE_AUTH", raising=False)
    client, engine = _build_client(tmp_path, with_key_value=False)
    _setup_admin(client)

    response = _login(client, "en")

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert SESSION_COOKIE_NAME in response.cookies
    assert response.cookies.get("NEXT_LOCALE") == "en"
    status = client.get(
        "/api/v1/auth/status",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={response.cookies[SESSION_COOKIE_NAME]}"},
    )
    assert status.status_code == 200
    assert status.json()["locale"] is None
    asyncio.run(engine.dispose())
