"""Ruble balance: prices, charges, refunds, presentation charges, YooKassa top-ups."""

import asyncio
import io
import json
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.middleware.base import BaseHTTPMiddleware

from api.v1.auth.context import (
    reset_current_owner_id,
    reset_current_owner_is_admin,
    set_current_owner_id,
    set_current_owner_is_admin,
)
from api.v1.billing import router as billing_router
from api.v1.studio import router as studio_router
from models.sql.billing import BillingAccount, BillingEntry, BillingPayment
from models.sql.image_asset import ImageAsset
from models.sql.user import User
from services.billing import ledger, payments, pricing, settings, yookassa
from services.database import get_async_session
from services.studio.arckep import StudioProviderError
from services.studio.models import MODELS
from utils.i18n.middleware import LocaleMiddleware


# ---------------------------------------------------------------- prices


def test_prices_match_the_standalone_studio():
    table = pricing.price_table()
    assert table["studio"]["nano_banana_2"]["resolution"] == {"1K": 12, "2K": 18, "4K": 27}
    assert table["studio"]["nano_banana_pro"]["resolution"] == {"1K": 25, "2K": 25, "4K": 39}
    assert table["studio"]["chatgpt_images_2"]["quality"] == {"draft": 2, "standard": 11, "high": 38}
    assert table["per_slide"] == 10
    gpt = MODELS["chatgpt_images_2"]
    assert pricing.image_price(gpt, quality="draft", count=4) == 6  # ceil(1.45 * 4), as the original
    assert pricing.image_price(gpt, quality="nonsense") == 11
    assert pricing.image_price(MODELS["nano_banana_2"], count=3) == 12  # one image per Gemini request
    assert pricing.presentation_price(5) == 50


def test_settings_parse_and_clamp(monkeypatch):
    monkeypatch.setenv("BILLING_PRICE_PER_SLIDE", "abc")
    assert settings.price_per_slide() == 10
    monkeypatch.setenv("BILLING_PRICE_PER_SLIDE", "-5")
    assert settings.price_per_slide() == 0
    monkeypatch.setenv("BILLING_SIGNUP_BONUS", " 250 ")
    assert settings.signup_bonus() == 250
    monkeypatch.setenv("BILLING_ENABLED", "false")
    assert settings.billing_enabled() is False
    monkeypatch.setenv("BILLING_OFFER_URL", "javascript:alert(1)")
    assert settings.offer_url() is None


# ---------------------------------------------------------------- ledger


@pytest.fixture
def db(monkeypatch, tmp_path):
    """A file SQLite database (real concurrent transactions) with two users."""
    for name in ("BILLING_ENABLED", "BILLING_PRICE_PER_SLIDE", "BILLING_SIGNUP_BONUS", "YOOKASSA_SHOP_ID", "YOOKASSA_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'billing.db'}", connect_args={"timeout": 30}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    users = {"alice": uuid.uuid4(), "bob": uuid.uuid4(), "admin": uuid.uuid4()}

    async def create():
        async with engine.begin() as connection:
            for table in (User.__table__, ImageAsset.__table__, BillingAccount.__table__, BillingEntry.__table__, BillingPayment.__table__):
                await connection.run_sync(table.create)
        async with maker() as session:
            for name, user_id in users.items():
                session.add(User(id=user_id, username=name, hashed_password="x", is_superuser=name == "admin"))
            await session.commit()

    asyncio.run(create())
    monkeypatch.setattr(ledger, "async_session_maker", maker)
    monkeypatch.setattr(payments, "async_session_maker", maker)
    monkeypatch.setattr(billing_router, "async_session_maker", maker)
    yield users, maker
    asyncio.run(engine.dispose())


def run(coroutine):
    return asyncio.run(coroutine)


def test_signup_bonus_once_and_simple_charges(db):
    users, _ = db
    alice = users["alice"]
    assert run(ledger.balance_of(alice)) == 100
    assert run(ledger.balance_of(alice)) == 100  # not granted twice
    charged = run(ledger.charge(alice, 30, reason="studio.generate"))
    assert charged.amount == 30 and run(ledger.balance_of(alice)) == 70
    with pytest.raises(ledger.InsufficientFunds) as error:
        run(ledger.charge(alice, 71, reason="studio.generate"))
    assert (error.value.needed, error.value.balance) == (71, 70)
    assert run(ledger.balance_of(alice)) == 70
    assert run(ledger.charge(None, 30, reason="x")) == ledger.FREE
    run(ledger.refund(charged))
    run(ledger.refund(charged))  # a second refund changes nothing
    assert run(ledger.balance_of(alice)) == 100
    kinds = [entry.kind for entry in run(ledger.history(alice))]
    assert kinds == ["refund", "charge", "bonus"]


def test_concurrent_charges_never_overspend(db):
    users, _ = db
    bob = users["bob"]
    run(ledger.balance_of(bob))  # 100

    async def many():
        async def one():
            try:
                return await ledger.charge(bob, 12, reason="studio.storyboard")
            except ledger.InsufficientFunds:
                return None

        return await asyncio.gather(*(one() for _ in range(20)))

    results = run(many())
    assert sum(1 for item in results if item) == 8
    assert run(ledger.balance_of(bob)) == 4
    entries = run(ledger.history(bob, 100))
    assert [entry.balance_after for entry in entries if entry.kind == "charge"] == sorted(
        [entry.balance_after for entry in entries if entry.kind == "charge"]
    )
    assert min(entry.balance_after for entry in entries) >= 0


def test_presentation_charge_is_reused_until_the_slides_are_saved(db):
    users, _ = db
    alice = users["alice"]
    deck = uuid.uuid4()
    first = run(ledger.charge_presentation(alice, deck, 5))
    assert first.amount == 50 and run(ledger.balance_of(alice)) == 50
    # The tab was closed / the model failed: trying again is free.
    assert run(ledger.charge_presentation(alice, deck, 5)) == ledger.FREE
    # The stream checks "is anything paid" only (its outline may have ToC slides).
    assert run(ledger.charge_presentation(alice, deck, 7, top_up=False)) == ledger.FREE
    # One more slide in the outline costs one slide more.
    assert run(ledger.charge_presentation(alice, deck, 6)).amount == 10
    run(ledger.settle_presentation(alice, deck))
    # Generating the finished deck again is a new generation.
    assert run(ledger.charge_presentation(alice, deck, 4)).amount == 40
    assert run(ledger.balance_of(alice)) == 0
    run(ledger.refund_presentation(alice, deck))
    assert run(ledger.balance_of(alice)) == 40
    # After a refund the next generation is paid again (fresh idempotency key).
    assert run(ledger.charge_presentation(alice, deck, 4)).amount == 40


def test_double_click_pays_once(db):
    users, _ = db
    bob = users["bob"]
    deck = uuid.uuid4()

    async def both():
        return await asyncio.gather(ledger.charge_presentation(bob, deck, 3), ledger.charge_presentation(bob, deck, 3))

    results = run(both())
    assert sorted(result.amount for result in results) == [0, 30]
    assert run(ledger.balance_of(bob)) == 70


def test_admin_adjust_never_below_zero(db):
    users, _ = db
    alice = users["alice"]
    assert run(ledger.admin_adjust(alice, 50, mode="add", admin_id=users["admin"], note="gift")) == 150
    assert run(ledger.admin_adjust(alice, -500, mode="add", admin_id=None)) == 0
    assert run(ledger.admin_adjust(alice, 75, mode="set", admin_id=None)) == 75
    entry = run(ledger.history(alice))[0]
    assert entry.kind == "admin" and entry.amount == 75 and entry.balance_after == 75


def test_who_pays(monkeypatch):
    user = uuid.uuid4()
    owner = set_current_owner_id(user)
    admin = set_current_owner_is_admin(False)
    try:
        assert ledger.payer() == user
        set_current_owner_is_admin(True)
        assert ledger.payer() is None
        set_current_owner_is_admin(False)
        monkeypatch.setenv("BILLING_ENABLED", "off")
        assert ledger.payer() is None
    finally:
        reset_current_owner_is_admin(admin)
        reset_current_owner_id(owner)
    assert ledger.payer() is None  # no sign-in (single-user mode)


# ---------------------------------------------------------------- YooKassa


class FakeYooKassa:
    """Scripted YooKassa: remembers created payments, answers lookups from them."""

    def __init__(self):
        self.created: list[dict] = []
        self.payments: dict[str, dict] = {}
        self.fail_create = None
        self.saved_charge_status = "succeeded"

    async def create_payment(self, **kwargs):
        if self.fail_create:
            raise self.fail_create
        payment_id = f"pay-{len(self.created) + 1}"
        self.created.append(kwargs)
        self.payments[payment_id] = {
            "id": payment_id,
            "status": "pending",
            "paid": False,
            "amount": {"value": f"{kwargs['amount']:.2f}", "currency": "RUB"},
            "metadata": kwargs["metadata"],
        }
        return {**self.payments[payment_id], "confirmation": {"confirmation_url": f"https://pay.example/{payment_id}"}}

    async def charge_saved(self, **kwargs):
        payment_id = f"auto-{len(self.created) + 1}"
        self.created.append(kwargs)
        payment = {
            "id": payment_id,
            "status": self.saved_charge_status,
            "paid": self.saved_charge_status == "succeeded",
            "amount": {"value": f"{kwargs['amount']:.2f}", "currency": "RUB"},
            "metadata": kwargs["metadata"],
        }
        self.payments[payment_id] = payment
        return payment

    async def get_payment(self, payment_id):
        if payment_id not in self.payments:
            raise yookassa.YooKassaError("not found", 404)
        return self.payments[payment_id]

    def succeed(self, payment_id, *, save_card=False):
        payment = self.payments[payment_id]
        payment.update(status="succeeded", paid=True)
        if save_card:
            payment["payment_method"] = {"id": "pm-1", "saved": True, "card": {"last4": "4242", "card_type": "Visa"}}


@pytest.fixture
def kassa(monkeypatch):
    fake = FakeYooKassa()
    monkeypatch.setattr(payments, "client", lambda: fake)
    monkeypatch.setattr(billing_router, "client", lambda: fake)
    return fake


def test_topup_is_credited_once_after_yookassa_confirms(db, kassa):
    users, _ = db
    alice = users["alice"]
    created = run(payments.create_topup(alice, 500, email="a@example.com", save_card=True, return_url="https://p/billing?payment="))
    assert created["confirmation_url"] == "https://pay.example/pay-1"
    sent = kassa.created[0]
    assert sent["return_url"].endswith(created["invoice_id"]) and sent["email"] == "a@example.com"
    assert sent["save_method"] is True and sent["idempotence_key"] == created["invoice_id"]

    assert run(payments.verify("pay-1")) == "pending"  # not paid yet
    assert run(ledger.balance_of(alice)) == 100
    kassa.succeed("pay-1", save_card=True)
    assert run(payments.verify("pay-1")) == "completed"
    assert run(payments.verify("pay-1")) == "completed"  # webhook + return: still once
    assert run(ledger.balance_of(alice)) == 600
    payment = run(payments.check_payment(alice, created["invoice_id"]))
    assert payment.status == "completed"
    assert run(payments.check_payment(users["bob"], created["invoice_id"])) is None  # not Bob's

    async def account():
        async with ledger.async_session_maker() as session:
            return await session.get(BillingAccount, alice)

    saved = run(account())
    assert (saved.saved_method_id, saved.card_last4, saved.receipt_email) == ("pm-1", "4242", "a@example.com")


def test_tampered_or_foreign_payments_are_not_credited(db, kassa):
    users, _ = db
    alice = users["alice"]
    created = run(payments.create_topup(alice, 100, email="a@example.com", save_card=False, return_url="x"))
    kassa.succeed("pay-1")
    kassa.payments["pay-1"]["amount"]["value"] = "1.00"  # paid less than the invoice
    assert run(payments.verify("pay-1")) == "pending"
    kassa.payments["pay-1"]["amount"]["value"] = "100.00"
    kassa.payments["pay-1"]["metadata"]["user_id"] = str(users["bob"])
    assert run(payments.verify("pay-1")) == "pending"
    assert run(payments.verify("no-such-payment")) is None
    assert run(payments.apply_provider_state({"id": "x", "status": "succeeded", "metadata": {"invoice_id": "nope"}})) is None
    assert run(ledger.balance_of(alice)) == 100
    kassa.payments["pay-1"]["metadata"]["user_id"] = str(alice)
    kassa.payments["pay-1"]["status"] = "canceled"
    assert run(payments.check_payment(alice, created["invoice_id"])).status == "failed"


def test_topup_errors(db, kassa, monkeypatch):
    users, _ = db
    kassa.fail_create = yookassa.YooKassaError("receipt.customer.email is invalid", 400)
    with pytest.raises(payments.TopupRejected):
        run(payments.create_topup(users["alice"], 100, email="a@example.com", save_card=False, return_url="x"))
    kassa.fail_create = yookassa.YooKassaError("unavailable")
    with pytest.raises(payments.PaymentsUnavailable):
        run(payments.create_topup(users["alice"], 100, email="a@example.com", save_card=False, return_url="x"))
    monkeypatch.setattr(payments, "client", lambda: None)
    with pytest.raises(payments.PaymentsUnavailable):
        run(payments.create_topup(users["alice"], 100, email="a@example.com", save_card=False, return_url="x"))


def _with_card(maker, user_id, *, threshold=50, amount=500, balance=None):
    async def setup():
        async with maker() as session:
            await ledger._account(session, user_id)
            account = await session.get(BillingAccount, user_id)
            account.saved_method_id = "pm-1"
            account.receipt_email = "a@example.com"
            account.auto_topup_enabled = True
            account.auto_topup_threshold = threshold
            account.auto_topup_amount = amount
            if balance is not None:
                account.balance = balance
            session.add(account)
            await session.commit()

    run(setup())


def test_auto_topup_once_an_hour_and_off_after_three_failures(db, kassa):
    users, maker = db
    alice = users["alice"]
    _with_card(maker, alice, balance=10)
    assert run(payments.maybe_auto_topup(alice)) == "completed"
    assert run(ledger.balance_of(alice)) == 510
    assert kassa.created[-1]["method_id"] == "pm-1"
    run(ledger.charge(alice, 505, reason="x"))
    assert run(payments.maybe_auto_topup(alice)) is None  # within the hour

    bob = users["bob"]
    _with_card(maker, bob, balance=0)
    kassa.saved_charge_status = "canceled"

    async def reset_clock():
        async with maker() as session:
            account = await session.get(BillingAccount, bob)
            account.last_auto_topup_at = None
            session.add(account)
            await session.commit()

    for _ in range(3):
        run(reset_clock())
        assert run(payments.maybe_auto_topup(bob)) == "failed"

    async def enabled():
        async with maker() as session:
            return (await session.get(BillingAccount, bob)).auto_topup_enabled

    assert run(enabled()) is False


def test_parallel_charges_start_one_auto_topup(db, kassa):
    users, maker = db
    alice = users["alice"]
    _with_card(maker, alice, balance=0)

    async def many():
        return await asyncio.gather(*(payments.maybe_auto_topup(alice) for _ in range(5)))

    assert sorted(result or "" for result in run(many())) == ["", "", "", "", "completed"]
    assert run(ledger.balance_of(alice)) == 500


# ---------------------------------------------------------------- API


class _AsUser(BaseHTTPMiddleware):
    """Test stand-in for the session middleware: X-User / X-Admin headers."""

    async def dispatch(self, request, call_next):
        user = request.headers.get("x-user")
        owner = set_current_owner_id(uuid.UUID(user) if user else None)
        admin = set_current_owner_is_admin(request.headers.get("x-admin") == "1")
        try:
            return await call_next(request)
        finally:
            reset_current_owner_is_admin(admin)
            reset_current_owner_id(owner)


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (32, 32), (10, 20, 30)).save(out, "PNG")
    return out.getvalue()


@pytest.fixture
def api(db, kassa, monkeypatch, tmp_path):
    users, maker = db
    monkeypatch.setenv("APP_DATA_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("STUDIO_API_KEY", "ark-test")

    async def override():
        async with maker() as session:
            yield session

    app = FastAPI()
    app.add_middleware(_AsUser)
    app.add_middleware(LocaleMiddleware)
    app.include_router(studio_router.API_V1_STUDIO_ROUTER)
    app.include_router(billing_router.API_V1_BILLING_ROUTER)
    app.include_router(billing_router.API_V1_ADMIN_BILLING_ROUTER)
    app.dependency_overrides[get_async_session] = override
    scheduled: list = []
    monkeypatch.setattr(payments, "schedule_auto_topup", scheduled.append)
    client = TestClient(app)
    client.scheduled = scheduled
    headers = {name: {"x-user": str(user_id), "x-admin": "1" if name == "admin" else "0", "Cookie": "NEXT_LOCALE=ru"} for name, user_id in users.items()}
    return client, headers, users


def test_studio_charges_refunds_and_402(api, monkeypatch):
    client, headers, users = api

    async def fake_create(model, prompt, **kwargs):
        return [_png()]

    monkeypatch.setattr(studio_router, "create_images", fake_create)
    config = client.get("/api/v1/studio/config", headers=headers["alice"]).json()
    assert config["charged"] is True and config["prices"]["nano_banana_pro"]["resolution"]["1K"] == 25
    assert client.get("/api/v1/studio/config", headers=headers["admin"]).json()["charged"] is False

    ok = client.post("/api/v1/studio/generate", json={"prompt": "кот", "model": "nano_banana_pro"}, headers=headers["alice"])
    assert ok.status_code == 200
    assert client.get("/api/v1/billing/me", headers=headers["alice"]).json()["balance"] == 75
    assert client.scheduled == [users["alice"]]  # auto top-up is checked after a charge

    async def broken(model, prompt, **kwargs):
        raise StudioProviderError("boom", status=500)

    monkeypatch.setattr(studio_router, "create_images", broken)
    failed = client.post("/api/v1/studio/generate", json={"prompt": "кот", "model": "nano_banana_pro"}, headers=headers["alice"])
    assert failed.status_code == 502
    assert client.get("/api/v1/billing/me", headers=headers["alice"]).json()["balance"] == 75  # given back

    monkeypatch.setattr(studio_router, "create_images", fake_create)
    for _ in range(3):
        client.post("/api/v1/studio/generate", json={"prompt": "кот", "model": "nano_banana_pro"}, headers=headers["alice"])
    poor = client.post("/api/v1/studio/generate", json={"prompt": "кот", "model": "nano_banana_pro"}, headers=headers["alice"])
    assert poor.status_code == 402
    assert poor.json()["detail"] == "Недостаточно средств: нужно 25 ₽, на балансе 0 ₽."

    free = client.post("/api/v1/studio/generate", json={"prompt": "кот", "model": "nano_banana_pro"}, headers=headers["admin"])
    assert free.status_code == 200
    assert users["admin"] not in client.scheduled
    history = client.get("/api/v1/billing/history", headers=headers["alice"]).json()["entries"]
    assert [entry["kind"] for entry in history] == ["charge", "charge", "charge", "refund", "charge", "charge", "bonus"]


def test_billing_api_topup_flow_and_validation(api, kassa):
    client, headers, users = api
    me = client.get("/api/v1/billing/me", headers=headers["bob"]).json()
    assert me["enabled"] and not me["free"] and me["balance"] == 100 and me["payments_available"]
    assert me["topup_amounts"] == [100, 500, 1000, 2000] and me["card"] is None
    assert client.get("/api/v1/billing/me").json()["enabled"] is False  # single-user mode

    bad = [
        ({"amount": 777, "email": "b@example.com"}, 400),
        ({"amount": 500, "email": "not-an-email"}, 400),
        ({"amount": 500, "email": "b@example.com", "save_card": True}, 400),
        ({"amount": "lots", "email": "b@example.com"}, 422),
    ]
    for body, status in bad:
        assert client.post("/api/v1/billing/topup", json=body, headers=headers["bob"]).status_code == status

    created = client.post(
        "/api/v1/billing/topup",
        json={"amount": 500, "email": "b@example.com", "save_card": True, "consent": True},
        headers={**headers["bob"], "Host": "presenton.example", "X-Forwarded-Proto": "https"},
    )
    assert created.status_code == 200
    invoice = created.json()["invoice_id"]
    assert kassa.created[-1]["return_url"] == f"https://presenton.example/billing?payment={invoice}"

    # A forged webhook body changes nothing: YooKassa still says "pending".
    forged = {"event": "payment.succeeded", "object": {"id": "pay-1", "status": "succeeded", "amount": {"value": "500.00"}}}
    assert client.post(billing_router.WEBHOOK_PATH, json=forged).status_code == 200
    assert client.get("/api/v1/billing/me", headers=headers["bob"]).json()["balance"] == 100
    assert client.post(billing_router.WEBHOOK_PATH, content=b"{not json").status_code == 400

    kassa.succeed("pay-1", save_card=True)
    assert client.post(billing_router.WEBHOOK_PATH, json=forged).status_code == 200
    checked = client.post(f"/api/v1/billing/payments/{invoice}/check", headers=headers["bob"]).json()
    assert checked["status"] == "completed" and checked["balance"] == 600
    assert client.post(f"/api/v1/billing/payments/{invoice}/check", headers=headers["alice"]).status_code == 404

    auto = client.put("/api/v1/billing/auto-topup", json={"enabled": True, "threshold": 100, "amount": 1000}, headers=headers["bob"])
    assert auto.status_code == 200 and auto.json()["auto_topup"]["enabled"] is True
    assert client.put("/api/v1/billing/auto-topup", json={"enabled": True, "threshold": 5, "amount": 1000}, headers=headers["bob"]).status_code == 422
    assert client.put("/api/v1/billing/auto-topup", json={"enabled": True, "threshold": 100, "amount": 500}, headers=headers["alice"]).status_code == 400
    assert client.delete("/api/v1/billing/card", headers=headers["bob"]).status_code == 204
    me = client.get("/api/v1/billing/me", headers=headers["bob"]).json()
    assert me["card"] is None and me["auto_topup"]["enabled"] is False


def test_admin_billing_endpoints(api):
    client, headers, users = api
    adjusted = client.post(
        "/api/v1/admin/billing/adjust",
        json={"user_id": str(users["alice"]), "amount": 250, "mode": "add", "note": "подарок"},
        headers=headers["admin"],
    )
    assert adjusted.json()["balance"] == 350
    accounts = {row["username"]: row for row in client.get("/api/v1/admin/billing/accounts", headers=headers["admin"]).json()["accounts"]}
    assert accounts["alice"]["balance"] == 350 and accounts["admin"]["admin"] is True
    assert client.post(
        "/api/v1/admin/billing/adjust", json={"user_id": str(uuid.uuid4()), "amount": 5}, headers=headers["admin"]
    ).status_code == 404
    history = client.get(f"/api/v1/admin/billing/history/{users['alice']}", headers=headers["admin"]).json()
    assert history["entries"][0]["details"]["note"] == "подарок"
