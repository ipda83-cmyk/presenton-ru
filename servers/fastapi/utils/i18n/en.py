# English (source) backend messages. Keep keys and {placeholders} identical to
# ru.py; tests/unit/test_i18n.py enforces parity. Avoid literal braces.

MESSAGES: dict[str, str] = {
    # Session / auth
    "auth.unauthorized": "Unauthorized",
    "auth.setupRequired": "Login setup is required",
    "auth.adminSessionRequired": "Admin browser session required",
    "auth.assetNotFound": "Asset not found",
    "auth.assetAccessDenied": "Asset access denied",
    "auth.credentialsConfigured": "Credentials already configured",
    "auth.usernameTooShort": "Username must be at least {min} characters",
    # Admin panel
    "admin.activeUserNotFound": "Active user not found",
    "admin.apiKeyNotFound": "API key not found",
    "admin.apiKeyRevoked": "API key has been revoked",
    "admin.apiKeyCannotReveal": "This API key cannot be revealed",
    "admin.adminAccessRequired": "Admin access required",
    "admin.forbidden": "You are not allowed to access this resource",
    "admin.usernameExists": "Username already exists",
    "admin.userNotFound": "User not found",
    "admin.primaryPasswordManaged": "The primary administrator password is managed through deployment settings",
    "admin.primaryCannotDelete": "The primary administrator account cannot be deleted",
    # AI provider failures (shown in generation / settings)
    "provider.invalidApiKey": "Invalid API key. Please verify your API key and try again.",
    "provider.imageModeration": "An image request was blocked by the safety system. A placeholder image was used for that slide.",
    "provider.generic": "The AI provider returned an error. Please try again.",
    "provider.safetyBlocked": "The request was blocked by the provider's safety system. Please revise it and try again.",
    "provider.prefix": "{provider} {operation}",
    "provider.aiProvider": "AI provider",
    "provider.op.request": "request",
    "provider.op.apiRequest": "API request",
    "provider.op.imageGeneration": "image generation",
    "provider.op.modelValidation": "model validation",
    "provider.quotaUnavailable": "{prefix} failed because API quota is unavailable. Check {provider} API billing and the limits for the project that owns this API key.",
    "provider.forbidden": "{provider} rejected the request because the configured API key does not have access. Check the key permissions and selected model.",
    "provider.rateLimited": "{prefix} is temporarily rate limited. Please wait and try again.",
    "provider.modelUnavailable": "The selected {provider} model is not available. Choose another model or check model access.",
    "provider.failed": "{prefix} failed. Please try again.",
}

# Request validation (422): English keeps pydantic's own wording.
VALIDATION_MESSAGES: dict[str, str] = {}


# Backend HTTP error texts (see errors_en.py).
from utils.i18n.errors_en import ERRORS as _ERRORS  # noqa: E402

MESSAGES.update(_ERRORS)
