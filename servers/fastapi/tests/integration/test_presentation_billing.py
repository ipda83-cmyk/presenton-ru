"""Slides are paid once per generation: a broken run is retried for free, a new run pays."""

import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.v1.auth.context import (
    reset_current_owner_id,
    reset_current_owner_is_admin,
    set_current_owner_id,
    set_current_owner_is_admin,
)
from api.v1.ppt.endpoints import presentation as presentation_endpoint
from models.sql.billing import BillingAccount, BillingEntry, BillingPayment
from models.sql.presentation import PresentationModel, PresentationVersion
from models.sql.user import User
from services.billing import ledger, payments
from tests.conftest import FakeAsyncSession
from utils import slide_generation_resume

LAYOUT = {
    "id": "template-layout-1",
    "description": "Hero layout",
    "components": [
        {
            "id": "hero",
            "description": "Hero content",
            "elements": [{"type": "text", "decorative": False, "name": "headline", "min_length": 1, "max_length": 32}],
        }
    ],
}


def _presentation(presentation_id):
    now = datetime.now()
    return PresentationModel(
        id=presentation_id,
        version=PresentationVersion.V2_STANDARD,
        content="deck",
        n_slides=3,
        language="Russian",
        title="Deck",
        outlines={"slides": [{"content": "## One"}, {"content": "## Two"}, {"content": "## Three"}]},
        layout={"layouts": [LAYOUT]},
        structure={"slides": [0, 0, 0]},
        tone="default",
        verbosity="standard",
        instructions=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def paying_user(monkeypatch, tmp_path):
    monkeypatch.setattr(slide_generation_resume, "RETRY_DELAYS_SECONDS", (0.0, 0.0))
    monkeypatch.setattr(payments, "schedule_auto_topup", lambda _user: None)
    for name in ("BILLING_ENABLED", "BILLING_PRICE_PER_SLIDE", "BILLING_SIGNUP_BONUS"):
        monkeypatch.delenv(name, raising=False)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'billing.db'}")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid.uuid4()

    async def create():
        async with engine.begin() as connection:
            for table in (User.__table__, BillingAccount.__table__, BillingEntry.__table__, BillingPayment.__table__):
                await connection.run_sync(table.create)
        async with maker() as session:
            session.add(User(id=user_id, username="payer", hashed_password="x"))
            await session.commit()

    asyncio.run(create())
    monkeypatch.setattr(ledger, "async_session_maker", maker)
    owner = set_current_owner_id(user_id)
    admin = set_current_owner_is_admin(False)
    yield user_id, maker
    reset_current_owner_is_admin(admin)
    reset_current_owner_id(owner)
    asyncio.run(engine.dispose())


def _consume(presentation):
    async def go():
        session = FakeAsyncSession(get_results={presentation.id: presentation})
        response = await presentation_endpoint.stream_presentation(id=presentation.id, sql_session=session)
        return "".join([chunk async for chunk in response.body_iterator])

    return asyncio.run(go())


def test_stream_pays_once_per_generation(paying_user):
    user_id, maker = paying_user
    presentation = _presentation(uuid.uuid4())
    calls: list[int] = []
    slide_3_down = {"value": True}

    async def slide_content(_layout, *_args, **kwargs):
        calls.append(kwargs["slide_number"])
        if kwargs["slide_number"] == 3 and slide_3_down["value"]:
            raise HTTPException(status_code=504, detail="Request timed out")
        return {"hero": {"headline": "Slide"}, "__speaker_note__": "Note."}

    with patch.object(presentation_endpoint, "get_slide_content_from_type_and_outline", new=slide_content), patch.object(
        presentation_endpoint, "process_slide_and_fetch_assets", new=AsyncMock(return_value=[])
    ), patch.object(presentation_endpoint, "get_images_directory", return_value="/tmp"), patch.object(
        presentation_endpoint, "ImageGenerationService", return_value=Mock()
    ):
        # /prepare paid for 3 slides.
        assert asyncio.run(presentation_endpoint._charge_slides(presentation.id, 3)).amount == 30
        assert asyncio.run(ledger.balance_of(user_id)) == 70

        failed = _consume(presentation)  # the model fails on slide 3
        assert "Request timed out" in failed
        slide_3_down["value"] = False
        _consume(presentation)  # reconnect: no new charge
        assert asyncio.run(ledger.balance_of(user_id)) == 70

        async def entries():
            async with maker() as session:
                return list(await session.scalars(select(BillingEntry).where(BillingEntry.kind == "charge")))

        assert [entry.settled for entry in asyncio.run(entries())] == [True]  # saved -> settled

        # Calling the stream again after the slides were saved is a new, paid generation.
        calls.clear()
        _consume(presentation)
        assert calls == [1, 2, 3]
        assert asyncio.run(ledger.balance_of(user_id)) == 40


def test_stream_without_money_explains_instead_of_generating(paying_user):
    user_id, _ = paying_user
    asyncio.run(ledger.admin_adjust(user_id, 0, mode="set", admin_id=None))
    presentation = _presentation(uuid.uuid4())
    generate = AsyncMock()
    with patch.object(presentation_endpoint, "get_slide_content_from_type_and_outline", new=generate):
        body = _consume(presentation)
    assert '"retryable": false' in body and '"status": 402' in body
    assert "Недостаточно средств" in body or "Not enough funds" in body
    generate.assert_not_called()


def test_create_refuses_early_when_the_balance_is_short(paying_user):
    user_id, _ = paying_user
    asyncio.run(ledger.admin_adjust(user_id, 20, mode="set", admin_id=None))
    asyncio.run(presentation_endpoint._require_balance_for(2))  # 20 RUB is enough for 2 slides
    with pytest.raises(HTTPException) as error:
        asyncio.run(presentation_endpoint._require_balance_for(3))
    assert error.value.status_code == 402
