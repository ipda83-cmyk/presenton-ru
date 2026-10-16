"""RelaxNet Storage API: upload, delete and download project files.

Docs: https://relaxnet.pro/ru/docs (section "Хранилище и API"). Uploaded files
get a public CDN link and a fallback link on files.relaxdev.ru. Raster images
are converted to WebP unless webp=false, which would rename our files.
"""

from dataclasses import dataclass
import mimetypes
import os

import httpx


class StorageError(Exception):
    pass


@dataclass(frozen=True)
class UploadedObject:
    remote_path: str
    url: str
    fallback_url: str | None


class StorageClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=15.0), transport=transport
        )

    def close(self) -> None:
        self._client.close()

    def upload(self, local_path: str, folder: str) -> UploadedObject:
        name = os.path.basename(local_path)
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        with open(local_path, "rb") as handle:
            response = self._request(
                "POST",
                f"{self._base_url}/upload",
                files={"file": (name, handle, content_type)},
                data={"path": folder, "webp": "false"},
            )
        body = _json(response)
        remote_path = body.get("path")
        url = body.get("url")
        if not body.get("success") or not isinstance(remote_path, str) or not isinstance(url, str):
            raise StorageError(f"unexpected upload response: {str(body)[:300]}")
        fallback_url = body.get("fallbackUrl")
        return UploadedObject(
            remote_path=remote_path,
            url=url,
            fallback_url=fallback_url if isinstance(fallback_url, str) else None,
        )

    def delete(self, remote_path: str) -> None:
        response = self._request(
            "DELETE", f"{self._base_url}/files", params={"path": remote_path}, allow_404=True
        )
        if response.status_code != 404:
            _json(response)

    def download(self, urls: list[str], destination: str) -> None:
        """Save the first URL that answers to destination (written atomically)."""
        errors: list[str] = []
        directory = os.path.dirname(destination)
        os.makedirs(directory, exist_ok=True)
        temporary = os.path.join(
            directory, f".{os.path.basename(destination)}.storage-restore.tmp"
        )
        for url in urls:
            try:
                with self._client.stream("GET", url) as response:
                    if response.status_code != 200:
                        errors.append(f"{url}: HTTP {response.status_code}")
                        continue
                    with open(temporary, "wb") as handle:
                        for chunk in response.iter_bytes(1024 * 1024):
                            handle.write(chunk)
                os.replace(temporary, destination)
                return
            except (httpx.HTTPError, OSError) as error:
                errors.append(f"{url}: {error}")
            finally:
                if os.path.exists(temporary):
                    try:
                        os.remove(temporary)
                    except OSError:
                        pass
        raise StorageError("; ".join(errors) or "no download URL")

    def _request(self, method: str, url: str, *, allow_404: bool = False, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, url, headers=self._headers, **kwargs)
        except httpx.HTTPError as error:
            raise StorageError(f"{method} {url}: {error}") from error
        if response.status_code >= 400 and not (allow_404 and response.status_code == 404):
            raise StorageError(f"{method} {url}: HTTP {response.status_code} {response.text[:300]}")
        return response


def _json(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError as error:
        raise StorageError(f"not JSON: {response.text[:300]}") from error
    if not isinstance(body, dict):
        raise StorageError(f"unexpected response: {str(body)[:300]}")
    if body.get("success") is False:
        raise StorageError(str(body.get("error") or body)[:300])
    return body
