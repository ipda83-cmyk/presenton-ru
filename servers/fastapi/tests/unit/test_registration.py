import asyncio
import re
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.middlewares import SessionAuthMiddleware
from api.v1.auth import registration_router
from api.v1.auth.router import API_V1_AUTH_ROUTER
from api.v1.legal import router as legal_router
from models.sql.billing import BillingAccount, BillingEntry
from models.sql.key_value import KeyValueSqlModel
from models.sql.user import User
from services import legal
from services.accounts import mailer, registration, tokens
from services.billing import ledger
from services.database import get_async_session
from utils.i18n.middleware import LocaleMiddleware


@pytest.fixture
def stand(monkeypatch, tmp_path):
    """SQLite with the needed tables, captured letters, mail configured."""
    for name in ("BILLING_ENABLED", "BILLING_SIGNUP_BONUS", "BILLING_OFFER_URL", "SMARTCAPTCHA_CLIENT_KEY", "SMARTCAPTCHA_SERVER_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("USER_CONFIG_PATH", str(tmp_path / "userConfig.json"))
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.test")
    monkeypatch.setenv("PRESENTON_PUBLIC_URL", "https://studio.example.test")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'signup.db'}", connect_args={"timeout": 30})
    maker = async_sessionmaker(engine, expire_on_commit=False)
    admin_id = uuid.uuid4()

    async def create():
        async with engine.begin() as connection:
            for table in (User.__table__, BillingAccount.__table__, BillingEntry.__table__, KeyValueSqlModel.__table__):
                await connection.run_sync(table.create)
        async with maker() as session:
            session.add(User(id=admin_id, username="admin", hashed_password="x", is_superuser=True))
            await session.commit()

    asyncio.run(create())
    for module in (ledger, registration, legal):
        monkeypatch.setattr(module, "async_session_maker", maker)
    import api.v1.auth.locale as locale_module

    if hasattr(locale_module, "async_session_maker"):
        monkeypatch.setattr(locale_module, "async_session_maker", maker)

    letters: list[dict] = []

    async def send(to, subject, text, html):
        letters.append({"to": to, "subject": subject, "text": text})

    monkeypatch.setattr(mailer, "send", send)

    async def session_override():
        async with maker() as session:
            yield session

    app = FastAPI()
    app.add_middleware(LocaleMiddleware)
    app.include_router(API_V1_AUTH_ROUTER)
    app.include_router(registration_router.API_V1_REGISTRATION_ROUTER)
    app.include_router(registration_router.API_V1_ADMIN_REGISTRATION_ROUTER)
    app.include_router(legal_router.API_V1_LEGAL_ROUTER)
    app.include_router(legal_router.API_V1_ADMIN_LEGAL_ROUTER)
    app.dependency_overrides[get_async_session] = session_override
    asyncio.run(registration.save_settings({"open": True}))
    yield {"app": app, "maker": maker, "letters": letters}
    asyncio.run(engine.dispose())


def _client(stand, ip="77.88.55.60"):
    return TestClient(stand["app"], headers={"X-Forwarded-For": f"{ip}, 10.80.0.20"})


def _signup(client, email="anna@example.com", **extra):
    body = {"email": email, "password": "long-password-1", "accept_offer": True, "accept_privacy": True, **extra}
    return client.post("/api/v1/auth/register", json=body)


def _link(letter):
    return re.search(r"token=([\w.\-]+)", letter["text"]).group(1)


async def _user(maker, email):
    async with maker() as session:
        return await session.scalar(select(User).where(User.username == email))


def test_sign_up_signs_in_and_sends_a_confirmation(stand):
    client = _client(stand)
    response = _signup(client, "Anna@Example.com")
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "anna@example.com"
    assert response.json()["verified"] is False and response.json()["letter_sent"] is True
    assert client.get("/api/v1/auth/status").json()["authenticated"] is True
    letter = stand["letters"][-1]
    assert letter["to"] == "anna@example.com"
    assert "https://studio.example.test/verify-email?token=" in letter["text"]


def test_no_bonus_until_the_e_mail_is_confirmed_then_once(stand):
    client = _client(stand)
    _signup(client)
    user = asyncio.run(_user(stand["maker"], "anna@example.com"))
    assert asyncio.run(ledger.balance_of(user.id)) == 0

    token = _link(stand["letters"][-1])
    first = client.post("/api/v1/auth/verify-email", json={"token": token}).json()
    assert first == {"verified": True, "bonus": 100}
    again = client.post("/api/v1/auth/verify-email", json={"token": token}).json()
    assert again["bonus"] == 0
    assert asyncio.run(ledger.balance_of(user.id)) == 100


def test_wrong_links_are_refused(stand):
    client = _client(stand)
    _signup(client)
    token = _link(stand["letters"][-1])
    assert client.post("/api/v1/auth/verify-email", json={"token": token[:-3] + "abc"}).status_code == 400
    # A confirmation link does not reset the password.
    assert client.post("/api/v1/auth/password/reset", json={"token": token, "password": "new-password-1"}).status_code == 400


def test_sign_up_checks(stand):
    client = _client(stand)
    assert _signup(client, accept_privacy=False).status_code == 422
    assert _signup(client, "not-an-address").status_code == 422
    assert _signup(client, "bot@mailinator.com").status_code == 422
    assert _signup(client, "bot@inbox.yopmail.com").status_code == 422
    asyncio.run(registration.save_settings({"open": True, "blocked_domains": ["spam.example"]}))
    assert _signup(client, "bot@spam.example").status_code == 422
    assert _signup(client).status_code == 200
    assert _signup(_client(stand, "5.45.192.10"), "ANNA@example.com").status_code == 409


def test_sign_ups_per_address_are_limited(stand):
    client = _client(stand)
    for index in range(3):
        assert _signup(client, f"user{index}@example.com").status_code == 200
    assert _signup(client, "user9@example.com").status_code == 429
    assert _signup(_client(stand, "5.45.192.10"), "user9@example.com").status_code == 200


def test_closed_sign_up_and_mail_requirement(stand, monkeypatch):
    asyncio.run(registration.save_settings({"open": False}))
    client = _client(stand)
    assert client.get("/api/v1/auth/registration").json()["open"] is False
    assert _signup(client).status_code == 403
    monkeypatch.delenv("SMTP_HOST")
    assert client.put("/api/v1/admin/registration", json={"open": True}).status_code == 400
    state = client.get("/api/v1/admin/registration").json()
    assert state["mail"] == {"configured": False, "missing": ["SMTP_HOST"]}


def test_password_reset_works_once_and_signs_out_other_sessions(stand):
    client = _client(stand)
    _signup(client)
    other = _client(stand)
    assert other.post("/api/v1/auth/login", json={"username": "anna@example.com", "password": "long-password-1"}).status_code == 200

    assert client.post("/api/v1/auth/password/forgot", json={"email": "nobody@example.com"}).json() == {"sent": True}
    before = len(stand["letters"])
    assert client.post("/api/v1/auth/password/forgot", json={"email": "anna@example.com"}).json() == {"sent": True}
    assert len(stand["letters"]) == before + 1
    token = _link(stand["letters"][-1])
    assert "/reset-password?token=" in stand["letters"][-1]["text"]

    reset = client.post("/api/v1/auth/password/reset", json={"token": token, "password": "brand-new-pass"})
    assert reset.status_code == 200 and reset.json()["verified"] is True
    assert client.post("/api/v1/auth/password/reset", json={"token": token, "password": "another-pass-1"}).status_code == 400
    assert other.get("/api/v1/auth/status").json()["authenticated"] is False
    login = _client(stand).post("/api/v1/auth/login", json={"username": "anna@example.com", "password": "brand-new-pass"})
    assert login.status_code == 200
    user = asyncio.run(_user(stand["maker"], "anna@example.com"))
    assert asyncio.run(ledger.balance_of(user.id)) == 100  # the link proved the address


def test_letters_are_limited(stand):
    client = _client(stand)
    _signup(client)
    for _ in range(3):
        assert client.post("/api/v1/auth/verify-email/resend").json()["sent"] is True
    assert client.post("/api/v1/auth/verify-email/resend").status_code == 429
    # Asking for confirmations does not lock the password reset.
    assert client.post("/api/v1/auth/password/forgot", json={"email": "anna@example.com"}).status_code == 200


def test_documents_are_public_and_edited_by_administrators(stand):
    client = _client(stand)
    assert client.get("/api/v1/legal/offer").json()["body"] == ""
    assert client.get("/api/v1/auth/registration").json()["offer_url"] is None
    saved = client.put("/api/v1/admin/legal/offer", json={"title": "Публичная оферта", "body": "## 1. Термины\nТекст."}).json()
    assert saved["updated_at"]
    assert client.get("/api/v1/legal/offer").json()["title"] == "Публичная оферта"
    assert client.get("/api/v1/auth/registration").json()["offer_url"] == "/legal/offer"
    assert client.get("/api/v1/legal/secret").status_code == 404


def test_sign_up_and_documents_are_reachable_without_a_session():
    public = SessionAuthMiddleware._PUBLIC_AUTH_PATHS
    for path in ("/api/v1/auth/register", "/api/v1/auth/verify-email", "/api/v1/auth/password/forgot", "/api/v1/auth/password/reset", "/api/v1/auth/registration"):
        assert path in public
    assert "/api/v1/auth/verify-email/resend" not in public
    middleware = SessionAuthMiddleware(app=FastAPI())
    assert middleware._requires_auth("/api/v1/legal/offer") is False
    assert middleware._requires_auth("/api/v1/admin/legal/offer") is True


@pytest.mark.parametrize(
    "header, expected",
    [
        ("77.88.55.60, 10.80.0.20", "77.88.55.60"),
        ("1.1.1.1, 77.88.55.60, 10.80.0.20, 127.0.0.1", "77.88.55.60"),  # a forged first hop is ignored
        ("garbage, 10.0.0.1", "testclient"),
        ("", "testclient"),
    ],
)
def test_the_visitor_address_behind_the_proxies(header, expected):
    app = FastAPI()

    @app.get("/ip")
    async def ip(request: registration.Request):
        return {"ip": registration.client_ip(request)}

    headers = {"X-Forwarded-For": header} if header else {}
    assert TestClient(app).get("/ip", headers=headers).json()["ip"] == expected


def test_captcha(monkeypatch):
    assert asyncio.run(registration.captcha_passed(None, "1.2.3.4")) is True  # no keys: no captcha
    monkeypatch.setenv("SMARTCAPTCHA_CLIENT_KEY", "client")
    monkeypatch.setenv("SMARTCAPTCHA_SERVER_KEY", "server")
    assert asyncio.run(registration.captcha_passed(None, "1.2.3.4")) is False
    answers = {"good": {"status": "ok"}, "bad": {"status": "failed"}}
    seen = {}

    class FakeResponse:
        def __init__(self, token):
            self.status = 200
            self.token = token

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def json(self, content_type=None):
            return answers[self.token]

    class FakeSession:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def post(self, url, data):
            seen.update(data)
            return FakeResponse(data["token"])

    monkeypatch.setattr(registration.aiohttp, "ClientSession", FakeSession)
    assert asyncio.run(registration.captcha_passed("good", "1.2.3.4")) is True
    assert seen == {"secret": "server", "token": "good", "ip": "1.2.3.4"}
    assert asyncio.run(registration.captcha_passed("bad", "1.2.3.4")) is False


def test_tokens_expire_and_know_their_purpose(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_CONFIG_PATH", str(tmp_path / "userConfig.json"))
    user = User(id=uuid.uuid4(), username="anna@example.com", hashed_password="h1", is_active=True, auth_version=1)
    token = tokens.make(user, "reset")
    payload = tokens.read(token, "reset")
    assert payload and tokens.matches(user, payload)
    assert tokens.read(token, "verify") is None
    user.hashed_password = "h2"
    assert not tokens.matches(user, payload)  # used once: the password changed
    monkeypatch.setattr(tokens.time, "time", lambda: 10**10)
    assert tokens.read(tokens.make(user, "verify"), "verify") is not None
    monkeypatch.undo()


def test_letters_in_both_languages():
    subject, text, html = mailer.letter("verify", "ru", "https://x.test/verify-email?token=a&b=<c>")
    assert "Подтвердите" in subject and "https://x.test/verify-email?token=a&b=<c>" in text
    assert "&lt;c&gt;" in html and "<c>" not in html
    assert "Confirm" in mailer.letter("verify", "en", "https://x.test")[0]
