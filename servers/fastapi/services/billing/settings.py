"""Billing settings (administrator settings or environment)."""

from utils.get_env import (
    get_billing_enabled_env,
    get_billing_offer_url_env,
    get_billing_price_per_slide_env,
    get_billing_signup_bonus_env,
    get_yookassa_api_url_env,
    get_yookassa_secret_key_env,
    get_yookassa_shop_id_env,
    get_yookassa_vat_code_env,
)

DEFAULT_PRICE_PER_SLIDE = 10
DEFAULT_SIGNUP_BONUS = 100
DEFAULT_YOOKASSA_API_URL = "https://api.yookassa.ru/v3"
# 1 = no VAT (the seller is on a simplified tax system); see 54-FZ receipt codes.
DEFAULT_VAT_CODE = 1

# Fixed amounts (YooKassa asks shops for fixed prices) with what they roughly buy.
TOPUP_AMOUNTS = (100, 500, 1000, 2000)
AUTO_TOPUP_THRESHOLD_RANGE = (50, 500)
AUTO_TOPUP_AMOUNT_RANGE = (100, 5000)


def _whole(value: str | None, default: int, low: int, high: int) -> int:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return min(max(number, low), high)


def billing_enabled() -> bool:
    return (get_billing_enabled_env() or "").strip().lower() not in ("false", "0", "no", "off")


def price_per_slide() -> int:
    return _whole(get_billing_price_per_slide_env(), DEFAULT_PRICE_PER_SLIDE, 0, 10_000)


def signup_bonus() -> int:
    return _whole(get_billing_signup_bonus_env(), DEFAULT_SIGNUP_BONUS, 0, 100_000)


def offer_url() -> str | None:
    value = (get_billing_offer_url_env() or "").strip()
    return value if value.startswith(("https://", "http://")) else None


def yookassa_credentials() -> tuple[str, str] | None:
    shop_id = (get_yookassa_shop_id_env() or "").strip()
    secret = (get_yookassa_secret_key_env() or "").strip()
    return (shop_id, secret) if shop_id and secret else None


def yookassa_api_url() -> str:
    return (get_yookassa_api_url_env() or "").strip().rstrip("/") or DEFAULT_YOOKASSA_API_URL


def vat_code() -> int:
    return _whole(get_yookassa_vat_code_env(), DEFAULT_VAT_CODE, 1, 12)
