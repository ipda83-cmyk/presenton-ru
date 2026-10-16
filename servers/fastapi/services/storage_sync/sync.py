"""Keep APP_DATA_DIRECTORY in the external storage and bring it back after a redeploy.

The local folder stays the working copy: every part of Presenton keeps reading
and writing files as before. In the background:

- new and changed files are uploaded every few seconds (a file is taken once it
  has not changed for a moment), and files deleted locally are deleted remotely;
- after a start, files known to the storage but missing locally are downloaded;
- a file asked for before that finished is downloaded on the spot
  (``restore_file_sync``: path resolver and the /app_data mount).

A file missing locally is never treated as deleted unless it was seen on the
disk by this process: after a redeploy the disk is empty, not the storage.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import logging
import os
import threading
import time

from sqlalchemy import delete, select

from models.sql.storage_object import StorageObject
from services.storage_sync.client import StorageClient, StorageError
from utils.datetime_utils import get_current_utc_datetime

logger = logging.getLogger(__name__)

# Never copied: the SQLite database (copying a live database file is unsafe and a
# hosted install uses PostgreSQL), mem0's local vector store, partial files.
EXCLUDED_TOP_LEVEL = {"mem0", "fastapi.db", "fastapi.db-journal", "fastapi.db-wal", "fastapi.db-shm"}
EXCLUDED_SUFFIXES = (".tmp", ".part", ".lock", ".storage-restore.tmp", ".crdownload")
MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024  # the storage accepts files up to 5 GB
SETTLE_SECONDS = 1.0
RESTORE_CONCURRENCY = 4
# A file that could not be downloaded (storage down, copy lost) is tried again
# after this long, not on every request.
RESTORE_RETRY_SECONDS = 60.0


@dataclass
class _Entry:
    remote_path: str
    url: str
    fallback_url: str | None
    sha256: str
    size: int

    @classmethod
    def from_row(cls, row: StorageObject) -> "_Entry":
        return cls(row.remote_path, row.url, row.fallback_url, row.sha256, row.size)

    def urls(self) -> list[str]:
        return [self.url] + ([self.fallback_url] if self.fallback_url else [])


def is_excluded(relative_path: str) -> bool:
    parts = relative_path.split("/")
    if parts[0] in EXCLUDED_TOP_LEVEL:
        return True
    name = parts[-1]
    return name.endswith(EXCLUDED_SUFFIXES) or name.startswith(".~")


def normalize_relative_path(relative_path: str) -> str | None:
    """'images/a.png' style path inside the data folder, or None if it escapes it."""
    raw = (relative_path or "").replace("\\", "/").lstrip("/")
    parts = [part for part in raw.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class StorageSync:
    def __init__(
        self,
        root: str,
        client: StorageClient,
        session_maker: Callable,
        *,
        prefix: str = "app_data",
        interval: float = 3.0,
        settle_seconds: float = SETTLE_SECONDS,
        excluded_prefixes: tuple[str, ...] = (),
    ):
        self.root = os.path.realpath(root)
        self.client = client
        self.session_maker = session_maker
        self.prefix = prefix
        self.interval = interval
        self.settle_seconds = settle_seconds
        # Folders recreated from the image on every start (bundled template assets).
        self.excluded_prefixes = tuple(excluded_prefixes)
        self.manifest: dict[str, _Entry] = {}
        # (mtime_ns, size) of files seen on the disk and known to match the storage.
        self._seen: dict[str, tuple[int, int]] = {}
        self._failures: dict[str, int] = {}
        self._restore_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._failed_restores: dict[str, float] = {}  # path -> monotonic time of the failure
        self._tasks: list[asyncio.Task] = []
        self._scan_lock = asyncio.Lock()
        self.restore_finished = asyncio.Event()

    # ------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        await self.load_manifest()
        self._tasks = [
            asyncio.create_task(self._restore_then_mark(), name="storage-restore"),
            asyncio.create_task(self._loop(), name="storage-upload"),
        ]
        logger.info(
            "Storage sync on: %d files known in the storage (folder %s)",
            len(self.manifest),
            self.prefix,
        )

    async def stop(self, timeout: float) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks = []
        try:
            await asyncio.wait_for(self.scan_once(final=True), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Storage sync: final upload did not finish in %.0f s", timeout)
        except Exception:
            logger.exception("Storage sync: final upload failed")
        self.client.close()

    async def _restore_then_mark(self) -> None:
        # Repeats while some files could not be downloaded (the storage may be
        # down right after a deploy).
        while True:
            try:
                await self.restore_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Storage sync: restore failed")
            self.restore_finished.set()
            if not self._pending_restores():
                return
            await asyncio.sleep(RESTORE_RETRY_SECONDS)

    def _pending_restores(self) -> list[str]:
        return [
            path
            for path in list(self.manifest)
            if not self.is_excluded(path) and not os.path.isfile(self.local_path(path))
        ]

    def is_excluded(self, relative_path: str) -> bool:
        return is_excluded(relative_path) or relative_path.startswith(self.excluded_prefixes)

    async def drop_excluded(self) -> int:
        """Delete copies of files that are no longer synced (e.g. bundled template assets)."""
        dropped = 0
        for relative in [path for path in self.manifest if self.is_excluded(path)]:
            try:
                await self._delete_remote(relative)
                dropped += 1
            except StorageError as error:
                logger.warning("Storage sync: cannot delete %s: %s", relative, error)
        return dropped

    async def _loop(self) -> None:
        try:
            await self.drop_excluded()
        except Exception:
            logger.exception("Storage sync: cleanup failed")
        while True:
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Storage sync: scan failed")
            await asyncio.sleep(self.interval)

    # ------------------------------------------------------------ manifest

    async def load_manifest(self) -> None:
        async with self.session_maker() as session:
            rows = (await session.execute(select(StorageObject))).scalars().all()
        self.manifest = {row.path: _Entry.from_row(row) for row in rows}

    async def _save_entry(self, relative_path: str, entry: _Entry) -> None:
        async with self.session_maker() as session:
            row = await session.get(StorageObject, relative_path)
            if row is None:
                row = StorageObject(path=relative_path, remote_path="", url="", sha256="", size=0)
            row.remote_path = entry.remote_path
            row.url = entry.url
            row.fallback_url = entry.fallback_url
            row.sha256 = entry.sha256
            row.size = entry.size
            row.updated_at = get_current_utc_datetime()
            session.add(row)
            await session.commit()
        self.manifest[relative_path] = entry

    async def _forget_entry(self, relative_path: str) -> None:
        async with self.session_maker() as session:
            await session.execute(delete(StorageObject).where(StorageObject.path == relative_path))
            await session.commit()
        self.manifest.pop(relative_path, None)

    # ------------------------------------------------------------ restore

    def local_path(self, relative_path: str) -> str:
        return os.path.join(self.root, *relative_path.split("/"))

    def restore_file_sync(self, relative_path: str) -> bool:
        """Download one known file if it is missing locally. Blocking; True if it is there now."""
        relative_path = normalize_relative_path(relative_path)
        if relative_path is None:
            return False
        destination = self.local_path(relative_path)
        if os.path.isfile(destination):
            return True
        entry = self.manifest.get(relative_path)
        if entry is None or self.is_excluded(relative_path):
            return False
        if relative_path in self._seen:
            return False  # was on this disk and got deleted: the next scan deletes the copy
        failed_at = self._failed_restores.get(relative_path)
        if failed_at is not None and time.monotonic() - failed_at < RESTORE_RETRY_SECONDS:
            return False
        with self._locks_guard:
            lock = self._restore_locks.setdefault(relative_path, threading.Lock())
        with lock:
            if os.path.isfile(destination):
                return True
            try:
                self.client.download(entry.urls(), destination)
            except StorageError as error:
                if failed_at is None:
                    logger.warning("Storage sync: cannot restore %s: %s", relative_path, error)
                self._failed_restores[relative_path] = time.monotonic()
                return False
            self._failed_restores.pop(relative_path, None)
            # The bytes match the storage copy: a later local delete must reach it.
            stat = os.stat(destination)
            self._seen[relative_path] = (stat.st_mtime_ns, stat.st_size)
        with self._locks_guard:
            self._restore_locks.pop(relative_path, None)
        return True

    def restore_absolute_path_sync(self, path: str) -> bool:
        """restore_file_sync for an absolute path inside the data folder."""
        try:
            candidate = os.path.abspath(path)
            if os.path.commonpath([candidate, self.root]) != self.root:
                return False
        except ValueError:
            return False
        relative = os.path.relpath(candidate, self.root).replace(os.sep, "/")
        return self.restore_file_sync(relative)

    async def restore_all(self) -> int:
        missing = self._pending_restores()
        if not missing:
            return 0
        logger.info("Storage sync: restoring %d files", len(missing))
        semaphore = asyncio.Semaphore(RESTORE_CONCURRENCY)
        restored = 0

        async def restore(path: str) -> None:
            nonlocal restored
            async with semaphore:
                if await asyncio.to_thread(self.restore_file_sync, path):
                    restored += 1

        await asyncio.gather(*(restore(path) for path in missing))
        logger.info("Storage sync: restored %d of %d files", restored, len(missing))
        return restored

    # ------------------------------------------------------------ upload

    def _walk(self) -> dict[str, tuple[int, int]]:
        found: dict[str, tuple[int, int]] = {}
        for directory, subdirectories, files in os.walk(self.root):
            relative_directory = os.path.relpath(directory, self.root).replace(os.sep, "/")
            if relative_directory == ".":
                relative_directory = ""
                subdirectories[:] = [name for name in subdirectories if name not in EXCLUDED_TOP_LEVEL]
            for name in files:
                relative = f"{relative_directory}/{name}" if relative_directory else name
                if self.is_excluded(relative):
                    continue
                full = os.path.join(directory, name)
                try:
                    if os.path.islink(full):
                        continue
                    stat = os.stat(full)
                except OSError:
                    continue
                found[relative] = (stat.st_mtime_ns, stat.st_size)
        return found

    async def scan_once(self, *, final: bool = False) -> dict[str, int]:
        async with self._scan_lock:
            return await self._scan(final=final)

    async def _scan(self, *, final: bool) -> dict[str, int]:
        stats = {"uploaded": 0, "deleted": 0, "failed": 0}
        # Only files seen before the walk started can be "deleted": one restored
        # while the walk ran may be missing from it and must not be deleted.
        seen_before_walk = dict(self._seen)
        found = await asyncio.to_thread(self._walk)
        now_ns = time.time_ns()
        for relative, signature in found.items():
            if self._seen.get(relative) == signature:
                continue
            mtime_ns, size = signature
            if not final and now_ns - mtime_ns < self.settle_seconds * 1e9:
                continue  # still being written
            if size > MAX_FILE_SIZE:
                if relative not in self._failures:
                    logger.warning("Storage sync: %s is over 5 GB, not copied", relative)
                    self._failures[relative] = 1
                continue
            try:
                if await self._upload_if_changed(relative, signature):
                    stats["uploaded"] += 1
                self._failures.pop(relative, None)
            except (StorageError, OSError) as error:
                stats["failed"] += 1
                count = self._failures.get(relative, 0) + 1
                self._failures[relative] = count
                if count in (1, 10, 100):
                    logger.warning("Storage sync: cannot upload %s (try %d): %s", relative, count, error)
        gone = [
            path
            for path, signature in seen_before_walk.items()
            if path not in found and self._seen.get(path) == signature
        ]
        for relative in gone:
            self._seen.pop(relative, None)
            if relative in self.manifest:
                try:
                    await self._delete_remote(relative)
                    stats["deleted"] += 1
                except StorageError as error:
                    logger.warning("Storage sync: cannot delete %s: %s", relative, error)
        if stats["uploaded"] or stats["deleted"]:
            logger.info(
                "Storage sync: %d uploaded, %d deleted", stats["uploaded"], stats["deleted"]
            )
        return stats

    async def _upload_if_changed(self, relative: str, signature: tuple[int, int]) -> bool:
        local = self.local_path(relative)
        digest = await asyncio.to_thread(_sha256, local)
        # The file may have changed while it was hashed; the next scan takes it.
        current = os.stat(local)
        if (current.st_mtime_ns, current.st_size) != signature:
            return False
        previous = self.manifest.get(relative)
        if previous and previous.sha256 == digest and previous.size == signature[1]:
            self._seen[relative] = signature
            return False
        folder = "/".join([self.prefix] + relative.split("/")[:-1])
        uploaded = await asyncio.to_thread(self.client.upload, local, folder)
        await self._save_entry(
            relative,
            _Entry(uploaded.remote_path, uploaded.url, uploaded.fallback_url, digest, signature[1]),
        )
        self._failed_restores.pop(relative, None)
        self._seen[relative] = signature
        if previous and previous.remote_path != uploaded.remote_path:
            try:
                await asyncio.to_thread(self.client.delete, previous.remote_path)
            except StorageError as error:
                logger.warning("Storage sync: old copy of %s left behind: %s", relative, error)
        return True

    async def _delete_remote(self, relative: str) -> None:
        entry = self.manifest[relative]
        await asyncio.to_thread(self.client.delete, entry.remote_path)
        await self._forget_entry(relative)
