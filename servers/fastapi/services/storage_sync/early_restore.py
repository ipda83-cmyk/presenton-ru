"""Bring back files that are read before FastAPI starts.

start.js runs this before it merges environment variables into userConfig.json:
that file holds the secret that signs sign-in sessions, and a new one would sign
everybody out after every redeploy. Never fails the start.

    python -m services.storage_sync.early_restore userConfig.json
"""

import os
import sys

from sqlalchemy import create_engine, inspect, select

from models.sql.storage_object import StorageObject
from services.storage_sync.client import StorageClient, StorageError
from services.storage_sync.sync import normalize_relative_path
from utils.db_utils import get_database_url_and_connect_args, to_sync_sqlalchemy_url
from utils.get_env import (
    get_app_data_directory_env,
    get_storage_api_base_url_env,
    get_storage_api_key_env,
    is_storage_sync_enabled,
)


def restore(paths: list[str]) -> int:
    app_data = get_app_data_directory_env()
    if not app_data or not is_storage_sync_enabled():
        return 0
    wanted = {
        path
        for path in (normalize_relative_path(raw) for raw in paths)
        if path and not os.path.isfile(os.path.join(app_data, *path.split("/")))
    }
    if not wanted:
        return 0
    database_url, _ = get_database_url_and_connect_args()
    engine = create_engine(to_sync_sqlalchemy_url(database_url))
    try:
        with engine.connect() as connection:
            if not inspect(connection).has_table(StorageObject.__tablename__):
                return 0
            rows = connection.execute(
                select(StorageObject.path, StorageObject.url, StorageObject.fallback_url).where(
                    StorageObject.path.in_(wanted)
                )
            ).all()
    finally:
        engine.dispose()
    if not rows:
        return 0
    client = StorageClient(get_storage_api_base_url_env(), get_storage_api_key_env() or "", timeout=30.0)
    restored = 0
    try:
        for path, url, fallback_url in rows:
            destination = os.path.join(app_data, *path.split("/"))
            try:
                client.download([url] + ([fallback_url] if fallback_url else []), destination)
                restored += 1
            except StorageError as error:
                print(f"Storage sync: cannot restore {path} before start: {error}", file=sys.stderr)
    finally:
        client.close()
    if restored:
        print(f"Storage sync: restored {restored} file(s) before start")
    return restored


def main(argv: list[str]) -> int:
    try:
        restore(argv)
    except Exception as error:  # never block the start
        print(f"Storage sync: early restore skipped: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
