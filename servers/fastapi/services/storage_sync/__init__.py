"""Copy of APP_DATA_DIRECTORY in an external storage (see sync.py).

Enabled by STORAGE_API_KEY (RelaxNet sets it when a storage key is generated).
"""

import logging
import os

from services.storage_sync.sync import StorageSync

logger = logging.getLogger(__name__)

_active: StorageSync | None = None


def get_storage_sync() -> StorageSync | None:
    return _active


async def start_storage_sync() -> StorageSync | None:
    global _active
    from services.database import async_session_maker
    from services.storage_sync.client import StorageClient
    from templates.default_templates import default_template_ids
    from utils.get_env import (
        get_app_data_directory_env,
        get_storage_api_base_url_env,
        get_storage_api_key_env,
        get_storage_sync_interval_env,
        get_storage_sync_prefix_env,
        is_storage_sync_enabled,
    )

    app_data = get_app_data_directory_env()
    if _active is not None or not app_data or not is_storage_sync_enabled():
        return _active
    os.makedirs(app_data, exist_ok=True)
    sync = StorageSync(
        app_data,
        StorageClient(get_storage_api_base_url_env(), get_storage_api_key_env() or ""),
        async_session_maker,
        prefix=get_storage_sync_prefix_env(),
        interval=get_storage_sync_interval_env(),
        excluded_prefixes=tuple(f"templates/{template_id}/" for template_id in default_template_ids()),
    )
    await sync.start()
    _active = sync
    return sync


async def stop_storage_sync() -> None:
    global _active
    from utils.get_env import get_storage_sync_shutdown_timeout_env

    sync, _active = _active, None
    if sync is not None:
        await sync.stop(get_storage_sync_shutdown_timeout_env())


def restore_missing_app_data_file(path: str) -> bool:
    """Bring back a file of the data folder from the storage if it is missing.

    Blocking; cheap when the sync is off or the file is already on the disk.
    """
    sync = _active
    if sync is None or os.path.isfile(path):
        return False
    try:
        return sync.restore_absolute_path_sync(path)
    except Exception:
        logger.exception("Storage sync: restore of %s failed", path)
        return False
