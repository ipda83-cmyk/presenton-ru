import asyncio
import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import FileResponse

from api.lifespan import app_lifespan
from api.middlewares import SessionAuthMiddleware, UserConfigEnvUpdateMiddleware
from api.v1.async_tasks.router import API_V1_ASYNC_TASKS_ROUTER
from api.v1.auth.router import API_V1_AUTH_ROUTER
from api.v1.admin.router import API_V1_ADMIN_ROUTER
from api.v1.mock.router import API_V1_MOCK_ROUTER
from api.v1.ppt.router import API_V1_PPT_ROUTER
from api.v1.studio.router import API_V1_STUDIO_ROUTER
from api.v1.studio.admin_router import API_V1_ADMIN_STUDIO_ROUTER
from api.v1.help.router import API_V1_ADMIN_HELP_ROUTER, API_V1_HELP_ROUTER
from api.v1.billing.router import API_V1_ADMIN_BILLING_ROUTER, API_V1_BILLING_ROUTER
from api.v1.webhook.router import API_V1_WEBHOOK_ROUTER
from api.v2.router import API_V2_ROUTER
from services.storage_sync import get_storage_sync
from utils.get_env import (
    get_app_data_directory_env,
    get_sentry_dsn_env,
    get_sentry_send_default_pii_env,
    get_sentry_traces_sample_rate_env,
)
from utils.i18n.middleware import LocaleMiddleware
from utils.i18n.validation import request_validation_exception_handler
from utils.mime_types import init_sandbox_safe_mimetypes
from utils.path_helpers import get_resource_path


init_sandbox_safe_mimetypes()


def _maybe_init_sentry() -> None:
    sentry_dsn = get_sentry_dsn_env()
    if not sentry_dsn:
        return

    try:
        import sentry_sdk
    except Exception:
        # Sentry SDK is optional in some runtime targets.
        return

    traces_sample_rate = get_sentry_traces_sample_rate_env()
    send_default_pii = get_sentry_send_default_pii_env()
    try:
        parsed_sample_rate = (
            float(traces_sample_rate) if traces_sample_rate is not None else 1.0
        )
    except ValueError:
        parsed_sample_rate = 1.0

    parsed_send_default_pii = (
        send_default_pii.lower() == "true" if send_default_pii is not None else True
    )

    sentry_sdk.init(
        dsn=sentry_dsn,
        send_default_pii=parsed_send_default_pii,
        traces_sample_rate=parsed_sample_rate,
    )


_maybe_init_sentry()

class AppDataStaticFiles(StaticFiles):
    """/app_data files; one missing after a redeploy is brought back from the storage."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            sync = get_storage_sync()
            if error.status_code != 404 or sync is None:
                raise
            if not await asyncio.to_thread(sync.restore_file_sync, path):
                raise
            return await super().get_response(path, scope)


app = FastAPI(lifespan=app_lifespan)
app.add_exception_handler(RequestValidationError, request_validation_exception_handler)

# Routers
app.include_router(API_V1_PPT_ROUTER)
app.include_router(API_V1_WEBHOOK_ROUTER)
app.include_router(API_V1_MOCK_ROUTER)
app.include_router(API_V1_AUTH_ROUTER)
app.include_router(API_V1_ADMIN_ROUTER)
app.include_router(API_V1_ASYNC_TASKS_ROUTER)
app.include_router(API_V1_STUDIO_ROUTER)
app.include_router(API_V1_ADMIN_STUDIO_ROUTER)
app.include_router(API_V1_HELP_ROUTER)
app.include_router(API_V1_ADMIN_HELP_ROUTER)
app.include_router(API_V1_BILLING_ROUTER)
app.include_router(API_V1_ADMIN_BILLING_ROUTER)
app.include_router(API_V2_ROUTER)

# Mount app_data and static assets (direct FastAPI access; nginx also serves /static in Docker).
app_data_dir = get_app_data_directory_env()
if app_data_dir:
    os.makedirs(app_data_dir, exist_ok=True)
    app.mount("/app_data", AppDataStaticFiles(directory=app_data_dir), name="app_data")

static_dir = get_resource_path("static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Electron serves Next.js and FastAPI from separate loopback ports. When its
# runtime Next.js origin is available, use that exact origin so credentialed
# requests remain standards-compliant. Docker stays same-origin behind nginx;
# the wildcard fallback preserves standalone FastAPI development behavior.
next_public_origin = (os.getenv("NEXT_PUBLIC_URL") or "").strip().rstrip("/")
origins = [next_public_origin] if next_public_origin else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(UserConfigEnvUpdateMiddleware)
app.add_middleware(SessionAuthMiddleware)
# Added after SessionAuthMiddleware so it wraps it: auth errors get localized too.
app.add_middleware(LocaleMiddleware)


@app.middleware("http")
async def static_icon_fallback_middleware(request: Request, call_next):
    """Serve placeholder when icon paths are missing (e.g. renamed Phosphor icons)."""
    response = await call_next(request)
    if response.status_code != 404:
        return response
    path = request.url.path
    if not path.startswith("/static/icons/"):
        return response
    placeholder = get_resource_path("static/icons/placeholder.svg")
    if not os.path.isfile(placeholder):
        return response
    return FileResponse(placeholder, media_type="image/svg+xml")
