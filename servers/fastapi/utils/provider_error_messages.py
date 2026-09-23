import json
import re
from typing import Any

from utils.i18n import t

# English source strings, kept for importers; user-facing output goes through
# ``t()`` (see utils/i18n) so it follows the request's UI locale.
INVALID_API_KEY_MESSAGE = "Invalid API key. Please verify your API key and try again."
IMAGE_MODERATION_MESSAGE = (
    "An image request was blocked by the safety system. "
    "A placeholder image was used for that slide."
)
GENERIC_PROVIDER_ERROR_MESSAGE = (
    "The AI provider returned an error. Please try again."
)


_INVALID_API_KEY_PATTERNS = (
    re.compile(r"\binvalid[_\s-]*api[_\s-]*key\b", re.IGNORECASE),
    re.compile(r"\bincorrect\s+api\s+key\b", re.IGNORECASE),
    re.compile(r"\bapi\s+key\s+(?:is\s+)?invalid\b", re.IGNORECASE),
    re.compile(r"\bno\s+api\s+key\b", re.IGNORECASE),
    re.compile(r"\bauthentication(?:_error|\s+error)?\b", re.IGNORECASE),
)


def _normalize_code(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _stringify_for_detection(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _combined_text(*values: Any) -> str:
    return " ".join(part for part in (_stringify_for_detection(v) for v in values) if part)


def looks_like_invalid_api_key_error(
    *,
    status_code: int | None = None,
    code: Any = None,
    error_type: Any = None,
    message: Any = None,
) -> bool:
    normalized_code = _normalize_code(code)
    normalized_type = _normalize_code(error_type)
    if normalized_code in {
        "invalid_api_key",
        "invalid_api_key_error",
        "authentication_error",
        "unauthorized",
    }:
        return True
    if normalized_type in {"authentication_error", "invalid_api_key"}:
        return True
    if status_code == 401:
        return True

    text = _combined_text(code, error_type, message)
    return any(pattern.search(text) for pattern in _INVALID_API_KEY_PATTERNS)


def _looks_like_moderation_block(
    *, code: Any = None, error_type: Any = None, message: Any = None
) -> bool:
    text = _combined_text(code, error_type, message).lower()
    return (
        _normalize_code(code) == "moderation_blocked"
        or "moderation_blocked" in text
        or ("safety system" in text and "image_generation" in text)
    )


def _looks_like_model_access_error(
    *, code: Any = None, message: Any = None
) -> bool:
    normalized_code = _normalize_code(code)
    if normalized_code in {"model_not_found", "model_not_available"}:
        return True

    text = _combined_text(code, message).lower()
    return "model" in text and (
        "not found" in text
        or "does not exist" in text
        or "do not have access" in text
        or "doesn't exist" in text
    )


_OPERATION_KEYS = {
    "request": "provider.op.request",
    "api request": "provider.op.apiRequest",
    "image generation": "provider.op.imageGeneration",
    "model validation": "provider.op.modelValidation",
}


def _provider_label(provider: str) -> str:
    label = (provider or "").strip()
    if not label or label == "AI provider":
        return t("provider.aiProvider")
    return label


def _operation_label(operation: str) -> str:
    label = (operation or "").strip() or "request"
    key = _OPERATION_KEYS.get(label.lower())
    return t(key) if key else label


def _provider_operation_prefix(provider: str, operation: str) -> str:
    return t(
        "provider.prefix",
        provider=_provider_label(provider),
        operation=_operation_label(operation),
    )


def safe_provider_error_detail(
    provider: str,
    operation: str,
    *,
    status_code: int | None = None,
    code: Any = None,
    error_type: Any = None,
    message: Any = None,
) -> str:
    if looks_like_invalid_api_key_error(
        status_code=status_code,
        code=code,
        error_type=error_type,
        message=message,
    ):
        return t("provider.invalidApiKey")

    if _looks_like_moderation_block(
        code=code,
        error_type=error_type,
        message=message,
    ):
        if "image" in (operation or "").lower():
            return t("provider.imageModeration")
        return t("provider.safetyBlocked")

    provider_label = _provider_label(provider)
    prefix = _provider_operation_prefix(provider, operation)
    normalized_code = _normalize_code(code)
    if normalized_code == "insufficient_quota":
        return t("provider.quotaUnavailable", prefix=prefix, provider=provider_label)

    if status_code == 403:
        return t("provider.forbidden", provider=provider_label)

    if status_code == 429 or normalized_code in {"rate_limit_exceeded", "rate_limit"}:
        return t("provider.rateLimited", prefix=prefix)

    if _looks_like_model_access_error(code=code, message=message):
        return t("provider.modelUnavailable", provider=provider_label)

    return t("provider.failed", prefix=prefix)


def safe_llm_provider_error_detail(
    *,
    status_code: int | None = None,
    message: Any = None,
) -> str:
    if looks_like_invalid_api_key_error(status_code=status_code, message=message):
        return t("provider.invalidApiKey")

    text = _stringify_for_detection(message).strip()
    if not text:
        return t("provider.generic")

    looks_like_raw_provider_payload = (
        text.startswith("{")
        or text.startswith("[")
        or "{'error'" in text
        or '"error"' in text
        or "Error code:" in text
        or "http" in text.lower()
    )
    if looks_like_raw_provider_payload:
        return safe_provider_error_detail(
            "AI provider",
            "API request",
            status_code=status_code,
            message=text,
        )

    return text
