"""Copy of the data folder in an external storage: upload, delete, restore after a redeploy."""

import asyncio
import json
import os
import time

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import services.storage_sync as storage_sync_module
import services.storage_sync.sync as sync_module
from models.sql.storage_object import StorageObject
from services.storage_sync.client import StorageClient, StorageError, UploadedObject
from services.storage_sync.sync import StorageSync, is_excluded, normalize_relative_path
from utils import get_env
from utils.db_utils import get_database_url_and_connect_args


class FakeStorage:
    """In-memory Storage API: object names get a counter prefix, like the real one's timestamp."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.counter = 0
        self.fail_uploads = False
        self.deleted: list[str] = []

    def upload(self, local_path: str, folder: str) -> UploadedObject:
        if self.fail_uploads:
            raise StorageError("HTTP 500")
        self.counter += 1
        remote = f"users/7/presenton/{folder}/{self.counter}-{os.path.basename(local_path)}"
        with open(local_path, "rb") as handle:
            self.objects[remote] = handle.read()
        return UploadedObject(remote, f"https://cdn.test/{remote}", f"https://files.test/{remote}")

    def delete(self, remote_path: str) -> None:
        self.deleted.append(remote_path)
        self.objects.pop(remote_path, None)

    def download(self, urls: list[str], destination: str) -> None:
        remote = urls[0].split("https://cdn.test/", 1)[1]
        if remote not in self.objects:
            raise StorageError("HTTP 404")
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as handle:
            handle.write(self.objects[remote])

    def close(self) -> None:
        pass


@pytest.fixture
def maker(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'sync.db'}")

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(StorageObject.__table__.create)

    asyncio.run(create())
    yield async_sessionmaker(engine, expire_on_commit=False)
    asyncio.run(engine.dispose())


def run(coroutine):
    return asyncio.run(coroutine)


def write(root, relative, content: bytes, *, age: float = 10.0):
    path = os.path.join(root, *relative.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(content)
    old = time.time() - age
    os.utime(path, (old, old))
    return path


def new_sync(root, storage, maker):
    sync = StorageSync(str(root), storage, maker, prefix="app_data")
    run(sync.load_manifest())
    return sync


def rows(maker):
    async def fetch():
        async with maker() as session:
            return {row.path: row for row in (await session.execute(select(StorageObject))).scalars()}

    return run(fetch())


def test_uploads_new_files_and_skips_databases_and_partial_files(tmp_path, maker):
    root = tmp_path / "app_data"
    storage = FakeStorage()
    write(root, "images/users/u1/photo.png", b"png")
    write(root, "uploads/users/u1/doc.pdf", b"pdf")
    write(root, "fastapi.db", b"sqlite")
    write(root, "mem0/index.bin", b"vectors")
    write(root, "exports/report.pptx.part", b"half")
    sync = new_sync(root, storage, maker)

    stats = run(sync.scan_once())

    assert stats["uploaded"] == 2
    saved = rows(maker)
    assert set(saved) == {"images/users/u1/photo.png", "uploads/users/u1/doc.pdf"}
    photo = saved["images/users/u1/photo.png"]
    assert photo.remote_path.startswith("users/7/presenton/app_data/images/users/u1/")
    assert photo.url.startswith("https://cdn.test/") and photo.fallback_url.startswith("https://files.test/")
    assert storage.objects[photo.remote_path] == b"png"
    # Nothing changed: nothing is uploaded again.
    assert run(sync.scan_once())["uploaded"] == 0
    assert storage.counter == 2


def test_a_file_still_being_written_waits_for_the_next_scan(tmp_path, maker):
    root = tmp_path / "app_data"
    storage = FakeStorage()
    write(root, "images/fresh.png", b"x", age=0)
    sync = new_sync(root, storage, maker)
    assert run(sync.scan_once())["uploaded"] == 0
    # On shutdown everything left is taken at once.
    assert run(sync.scan_once(final=True))["uploaded"] == 1


def test_changed_file_replaces_the_old_copy(tmp_path, maker):
    root = tmp_path / "app_data"
    storage = FakeStorage()
    path = write(root, "fonts/brand.woff2", b"v1")
    sync = new_sync(root, storage, maker)
    run(sync.scan_once())
    first = rows(maker)["fonts/brand.woff2"].remote_path

    write(root, "fonts/brand.woff2", b"version 2", age=5)
    assert run(sync.scan_once())["uploaded"] == 1
    second = rows(maker)["fonts/brand.woff2"]
    assert second.remote_path != first and storage.objects[second.remote_path] == b"version 2"
    assert first in storage.deleted and first not in storage.objects

    # Same bytes written again (new mtime): no upload.
    os.utime(path, (time.time() - 3, time.time() - 3))
    assert run(sync.scan_once())["uploaded"] == 0


def test_file_deleted_locally_is_deleted_in_the_storage(tmp_path, maker):
    root = tmp_path / "app_data"
    storage = FakeStorage()
    path = write(root, "exports/deck.pdf", b"pdf")
    sync = new_sync(root, storage, maker)
    run(sync.scan_once())
    remote = rows(maker)["exports/deck.pdf"].remote_path

    os.remove(path)
    # Asked for between the delete and the next scan: not brought back.
    assert sync.restore_file_sync("exports/deck.pdf") is False and not os.path.exists(path)
    assert run(sync.scan_once())["deleted"] == 1
    assert rows(maker) == {} and remote not in storage.objects


def test_redeploy_restores_files_and_never_deletes_what_is_not_restored_yet(tmp_path, maker):
    storage = FakeStorage()
    first_disk = tmp_path / "first"
    write(first_disk, "images/users/u1/a.png", b"a")
    write(first_disk, "pptx-to-json/users/u1/t.json", b"{}")
    first = new_sync(first_disk, storage, maker)
    run(first.scan_once())

    # New container: empty disk, same database and storage.
    second_disk = tmp_path / "second"
    second_disk.mkdir()
    second = new_sync(second_disk, storage, maker)
    assert run(second.scan_once())["deleted"] == 0  # missing locally is not "deleted"
    assert len(storage.objects) == 2

    assert run(second.restore_all()) == 2
    assert (second_disk / "images/users/u1/a.png").read_bytes() == b"a"
    assert (second_disk / "pptx-to-json/users/u1/t.json").read_bytes() == b"{}"
    # Restored files match the storage: nothing to upload.
    assert run(second.scan_once())["uploaded"] == 0
    assert storage.counter == 2


def test_restore_one_file_on_demand_and_refuse_paths_outside(tmp_path, maker, monkeypatch):
    storage = FakeStorage()
    old_disk = tmp_path / "old"
    write(old_disk, "uploads/users/u1/doc.pdf", b"doc")
    run(new_sync(old_disk, storage, maker).scan_once())

    disk = tmp_path / "new"
    disk.mkdir()
    sync = new_sync(disk, storage, maker)
    assert sync.restore_file_sync("uploads/users/u1/doc.pdf") is True
    assert (disk / "uploads/users/u1/doc.pdf").read_bytes() == b"doc"
    assert sync.restore_file_sync("uploads/users/u1/unknown.pdf") is False
    assert sync.restore_file_sync("../old/uploads/users/u1/doc.pdf") is False
    assert sync.restore_absolute_path_sync(str(tmp_path / "old" / "x")) is False
    # The storage fails (another fresh disk): the file is not asked for on every
    # request, but later again.
    disk = tmp_path / "newer"
    disk.mkdir()
    sync = new_sync(disk, storage, maker)
    saved = dict(storage.objects)
    storage.objects.clear()
    assert sync.restore_file_sync("uploads/users/u1/doc.pdf") is False
    storage.objects.update(saved)
    assert sync.restore_file_sync("uploads/users/u1/doc.pdf") is False  # still waiting
    monkeypatch.setattr(sync_module, "RESTORE_RETRY_SECONDS", 0.0)
    assert sync.restore_file_sync("uploads/users/u1/doc.pdf") is True


def test_upload_errors_are_retried(tmp_path, maker):
    root = tmp_path / "app_data"
    storage = FakeStorage()
    storage.fail_uploads = True
    write(root, "images/a.png", b"a")
    sync = new_sync(root, storage, maker)
    assert run(sync.scan_once())["failed"] == 1
    storage.fail_uploads = False
    assert run(sync.scan_once())["uploaded"] == 1


def test_path_resolver_brings_back_a_missing_file(tmp_path, maker, monkeypatch):
    from utils import asset_directory_utils

    storage = FakeStorage()
    old_disk = tmp_path / "old"
    write(old_disk, "images/users/u1/slide.png", b"img")
    run(new_sync(old_disk, storage, maker).scan_once())

    disk = tmp_path / "app_data"
    disk.mkdir()
    monkeypatch.setenv("APP_DATA_DIRECTORY", str(disk))
    monkeypatch.setenv("DISABLE_AUTH", "true")
    monkeypatch.setattr(storage_sync_module, "_active", new_sync(disk, storage, maker))

    resolved = asset_directory_utils.resolve_app_path_to_filesystem("/app_data/images/users/u1/slide.png")
    assert resolved == os.path.realpath(disk / "images/users/u1/slide.png")
    assert (disk / "images/users/u1/slide.png").read_bytes() == b"img"
    assert asset_directory_utils.resolve_app_path_to_filesystem("/app_data/images/nope.png") is None


def test_app_data_mount_brings_back_a_missing_file(tmp_path, maker, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.main import AppDataStaticFiles

    storage = FakeStorage()
    old_disk = tmp_path / "old"
    write(old_disk, "templates/custom/preview.png", b"preview")
    run(new_sync(old_disk, storage, maker).scan_once())

    disk = tmp_path / "app_data"
    disk.mkdir()
    app = FastAPI()
    app.mount("/app_data", AppDataStaticFiles(directory=str(disk)), name="app_data")
    client = TestClient(app)

    monkeypatch.setattr(storage_sync_module, "_active", None)
    assert client.get("/app_data/templates/custom/preview.png").status_code == 404

    monkeypatch.setattr(storage_sync_module, "_active", new_sync(disk, storage, maker))
    response = client.get("/app_data/templates/custom/preview.png")
    assert response.status_code == 200 and response.content == b"preview"
    assert client.get("/app_data/templates/custom/missing.png").status_code == 404


def test_storage_client_speaks_the_storage_api(tmp_path):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={
                "success": True,
                "url": "https://cdn.relaxdev.ru/users/7/p/app_data/images/1-a.png",
                "fallbackUrl": "https://files.relaxdev.ru/users/7/p/app_data/images/1-a.png",
                "path": "users/7/p/app_data/images/1-a.png",
                "webp": False,
            })
        if request.method == "DELETE":
            return httpx.Response(200, json={"success": True, "deleted": request.url.params["path"]})
        if request.url.host == "cdn.relaxdev.ru":
            return httpx.Response(503)
        return httpx.Response(200, content=b"bytes")

    client = StorageClient("https://relaxdev.ru/api/v1/storage/", "sk_rd_test", transport=httpx.MockTransport(handler))
    source = tmp_path / "a.png"
    source.write_bytes(b"png")
    uploaded = client.upload(str(source), "app_data/images")
    assert uploaded.remote_path == "users/7/p/app_data/images/1-a.png"
    upload = requests[0]
    assert str(upload.url) == "https://relaxdev.ru/api/v1/storage/upload"
    assert upload.headers["authorization"] == "Bearer sk_rd_test"
    body = upload.content.decode("latin-1")
    assert 'name="webp"\r\n\r\nfalse' in body and 'name="path"\r\n\r\napp_data/images' in body

    client.delete(uploaded.remote_path)
    assert requests[1].url.params["path"] == "users/7/p/app_data/images/1-a.png"

    # The CDN fails: the fallback link is used.
    destination = tmp_path / "restored" / "a.png"
    client.download([uploaded.url, uploaded.fallback_url], str(destination))
    assert destination.read_bytes() == b"bytes"
    assert not any(name.endswith(".tmp") for name in os.listdir(destination.parent))


def test_storage_client_reports_errors(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, content=json.dumps({"success": False, "error": "quota"}))
        return httpx.Response(404)

    client = StorageClient("https://relaxdev.ru/api/v1/storage", "k", transport=httpx.MockTransport(handler))
    source = tmp_path / "a.png"
    source.write_bytes(b"png")
    with pytest.raises(StorageError, match="quota"):
        client.upload(str(source), "app_data")
    client.delete("users/7/p/gone.png")  # already gone is fine
    with pytest.raises(StorageError):
        client.download(["https://cdn.relaxdev.ru/x"], str(tmp_path / "x"))
    assert not (tmp_path / "x").exists()


def test_settings_from_environment(monkeypatch):
    for name in ("STORAGE_API_KEY", "STORAGE_SYNC_ENABLED", "STORAGE_SYNC_PREFIX", "STORAGE_API_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    assert get_env.is_storage_sync_enabled() is False
    monkeypatch.setenv("STORAGE_API_KEY", " sk_rd_1 ")
    assert get_env.is_storage_sync_enabled() is True
    monkeypatch.setenv("STORAGE_SYNC_ENABLED", "false")
    assert get_env.is_storage_sync_enabled() is False
    assert get_env.get_storage_sync_prefix_env() == "app_data"
    monkeypatch.setenv("STORAGE_SYNC_PREFIX", "/../prod//data/")
    assert get_env.get_storage_sync_prefix_env() == "prod/data"
    assert get_env.get_storage_api_base_url_env() == "https://relaxdev.ru/api/v1/storage"
    monkeypatch.setenv("STORAGE_API_BASE_URL", "auto-generated-stub-for-build")
    assert get_env.get_storage_api_base_url_env() == "https://relaxdev.ru/api/v1/storage"


def test_excluded_and_normalized_paths():
    assert is_excluded("fastapi.db") and is_excluded("mem0/x") and is_excluded("images/.a.png.storage-restore.tmp")
    assert not is_excluded("images/fastapi.db") and not is_excluded("userConfig.json")
    assert normalize_relative_path("\\images\\a.png") == "images/a.png"
    assert normalize_relative_path("images/../../etc/passwd") is None
    assert normalize_relative_path("") is None


def test_postgres_scheme_from_hosts_is_accepted(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:secret@db.internal:5432/presenton")
    url, _ = get_database_url_and_connect_args()
    assert url == "postgresql+asyncpg://user:secret@db.internal:5432/presenton"


def test_background_restore_retries_while_the_storage_is_down(tmp_path, maker, monkeypatch):
    storage = FakeStorage()
    old_disk = tmp_path / "old"
    write(old_disk, "images/a.png", b"a")
    run(new_sync(old_disk, storage, maker).scan_once())
    saved = dict(storage.objects)
    storage.objects.clear()  # storage unreachable at start
    monkeypatch.setattr(sync_module, "RESTORE_RETRY_SECONDS", 0.05)

    disk = tmp_path / "new"
    disk.mkdir()
    sync = new_sync(disk, storage, maker)

    async def scenario():
        task = asyncio.create_task(sync._restore_then_mark())
        await sync.restore_finished.wait()
        assert not (disk / "images/a.png").exists()
        storage.objects.update(saved)  # back up
        await asyncio.wait_for(task, timeout=5)

    run(scenario())
    assert (disk / "images/a.png").read_bytes() == b"a"


def test_bundled_template_assets_are_not_synced_and_old_copies_are_dropped(tmp_path, maker):
    storage = FakeStorage()
    root = tmp_path / "app_data"
    write(root, "templates/general/static/bg.png", b"bundled")
    write(root, "templates/3f1c-custom/static/logo.png", b"custom")
    # An older version synced the bundled assets too.
    run(new_sync(root, storage, maker).scan_once())
    assert len(storage.objects) == 2

    sync = StorageSync(str(root), storage, maker, excluded_prefixes=("templates/general/",))
    run(sync.load_manifest())
    assert run(sync.drop_excluded()) == 1
    assert set(rows(maker)) == {"templates/3f1c-custom/static/logo.png"}
    write(root, "templates/general/static/new.png", b"bundled 2")
    assert run(sync.scan_once())["uploaded"] == 0
    assert sync.restore_file_sync("templates/general/static/bg.png") is True  # already on disk
    os.remove(root / "templates/general/static/bg.png")
    assert sync.restore_file_sync("templates/general/static/bg.png") is False


def test_user_config_is_restored_before_the_servers_start(tmp_path, monkeypatch):
    from services.storage_sync import early_restore

    db_path = tmp_path / "early.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(StorageObject.__table__.create)

    asyncio.run(create())
    maker_ = async_sessionmaker(engine, expire_on_commit=False)
    storage = FakeStorage()
    old_disk = tmp_path / "old"
    write(old_disk, "userConfig.json", b'{"AUTH_SECRET_KEY": "keep-me"}')
    run(new_sync(old_disk, storage, maker_).scan_once())
    asyncio.run(engine.dispose())

    disk = tmp_path / "app_data"
    disk.mkdir()
    monkeypatch.setenv("APP_DATA_DIRECTORY", str(disk))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_API_KEY", "sk_rd_test")
    monkeypatch.setattr(early_restore, "StorageClient", lambda *args, **kwargs: storage)

    assert early_restore.restore(["userConfig.json", "../etc/passwd"]) == 1
    assert json.loads((disk / "userConfig.json").read_text())["AUTH_SECRET_KEY"] == "keep-me"
    assert early_restore.restore(["userConfig.json"]) == 0  # already there
    monkeypatch.delenv("STORAGE_API_KEY")
    (disk / "userConfig.json").unlink()
    assert early_restore.restore(["userConfig.json"]) == 0  # sync off: nothing to do


def test_early_restore_never_fails_the_start(monkeypatch, tmp_path):
    from services.storage_sync import early_restore

    monkeypatch.setenv("APP_DATA_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("STORAGE_API_KEY", "sk_rd_test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:x@127.0.0.1:1/none")
    assert early_restore.main(["userConfig.json"]) == 0


def test_a_restored_file_deleted_right_away_is_deleted_in_the_storage(tmp_path, maker):
    storage = FakeStorage()
    old_disk = tmp_path / "old"
    write(old_disk, "exports/deck.pdf", b"pdf")
    run(new_sync(old_disk, storage, maker).scan_once())

    disk = tmp_path / "new"
    disk.mkdir()
    sync = new_sync(disk, storage, maker)
    assert run(sync.restore_all()) == 1
    (disk / "exports/deck.pdf").unlink()  # before any scan saw it
    assert run(sync.scan_once())["deleted"] == 1
    assert storage.objects == {} and rows(maker) == {}


def test_a_file_restored_while_the_disk_is_walked_is_not_deleted(tmp_path, maker, monkeypatch):
    storage = FakeStorage()
    old_disk = tmp_path / "old"
    write(old_disk, "images/a.png", b"a")
    run(new_sync(old_disk, storage, maker).scan_once())

    disk = tmp_path / "new"
    disk.mkdir()
    sync = new_sync(disk, storage, maker)
    real_walk = sync._walk

    def walk_then_restore():
        found = real_walk()  # the file is not there yet...
        assert sync.restore_file_sync("images/a.png")  # ...and comes back meanwhile
        return found

    monkeypatch.setattr(sync, "_walk", walk_then_restore)
    assert run(sync.scan_once())["deleted"] == 0
    assert len(storage.objects) == 1 and set(rows(maker)) == {"images/a.png"}
    monkeypatch.setattr(sync, "_walk", real_walk)
    assert run(sync.scan_once()) == {"uploaded": 0, "deleted": 0, "failed": 0}
