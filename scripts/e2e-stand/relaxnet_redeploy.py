"""Redeploys the way RelaxNet does them: the container disk is lost every time.

Presenton runs with PostgreSQL, traffic on port 8080 only, the data folder kept in
the (fake) RelaxNet Storage API, and placeholder values that the host puts into
variables the project does not define. The container is stopped, removed and
started again from scratch; users, balances and files must survive.

    python scripts/e2e-stand/relaxnet_redeploy.py

Needs Docker and the presenton-ru-production image (PRESENTON_IMAGE to change).
Presenton: http://127.0.0.1:5058, fake upstreams: http://127.0.0.1:9056.
"""

import os
import subprocess
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
os.environ.setdefault("E2E_BASE", "http://127.0.0.1:5058")
sys.path.insert(0, HERE)

from common import BASE, FAKE, check, fake, fake_log, png, summary  # noqa: E402

IMAGE = os.environ.get("PRESENTON_IMAGE", "presenton-ru-production:latest")
NETWORK = "presenton-e2e"
APP = "presenton-relax"
DB = "presenton-relax-pg"
FAKE_CONTAINER = "presenton-e2e-fake"
PLACEHOLDER = "auto-generated-stub-for-build"
ADMIN = {"username": "relax-admin", "password": "relax-admin-pass-1"}
USER = {"username": "relax-user", "password": "relax-user-pass-1"}


def docker(*args: str, check_result: bool = True) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check_result and result.returncode != 0:
        sys.exit(f"docker {' '.join(args[:3])}: {result.stderr.strip()[:400]}")
    return result.stdout


def container_logs() -> str:
    result = subprocess.run(["docker", "logs", APP], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.stdout + result.stderr


def mount(path: str) -> str:
    return os.path.join(ROOT, path)


def start_infrastructure() -> None:
    docker("network", "create", NETWORK, check_result=False)
    docker("rm", "-f", DB, check_result=False)
    docker("run", "-d", "--name", DB, "--network", NETWORK,
           "-e", "POSTGRES_USER=presenton", "-e", "POSTGRES_PASSWORD=pg-secret", "-e", "POSTGRES_DB=presenton",
           "postgres:16-alpine")
    docker("rm", "-f", FAKE_CONTAINER, check_result=False)
    docker("run", "-d", "--name", FAKE_CONTAINER, "--network", NETWORK, "-p", "127.0.0.1:9056:9000",
           "-v", f"{HERE}:/e2e", "--entrypoint", "/opt/venv/bin/python", IMAGE, "/e2e/fake_upstream.py")
    for _ in range(60):
        ready = subprocess.run(["docker", "exec", DB, "pg_isready", "-U", "presenton"], capture_output=True)
        try:
            fake_ok = requests.get(f"{FAKE}/control", timeout=2).ok
        except requests.RequestException:
            fake_ok = False
        if ready.returncode == 0 and fake_ok:
            return
        time.sleep(1)
    sys.exit("postgres or the fake upstream did not start")


def rewritten_nginx_conf() -> str:
    """nginx.conf as the RelaxNet builder leaves it: "listen 80" rewritten into "listen 8080"."""
    folder = os.path.join(HERE, ".relax-logs")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "nginx-rewritten.conf")
    with open(mount("nginx.conf"), encoding="utf-8") as source, open(path, "w", encoding="utf-8", newline="\n") as target:
        target.write(source.read().replace("    listen 80;", "    listen 8080;"))
    return path


def start_app() -> float:
    """A fresh container: no volume for /app_data. Returns the start time."""
    docker("rm", "-f", APP, check_result=False)
    started = time.time()
    docker(
        "run", "-d", "--name", APP, "--network", NETWORK, "-p", "127.0.0.1:5058:8080",
        "-v", f"{mount('servers/fastapi')}:/app/servers/fastapi",
        "-v", f"{mount('start.js')}:/app/start.js:ro",
        "-v", f"{rewritten_nginx_conf()}:/etc/nginx/nginx.conf:ro",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        # What the host sets for every container.
        "-e", "PORT=8080", "-e", "UVICORN_PORT=8080", "-e", "SERVER_PORT=8080",
        # Placeholders for variables the project does not define.
        "-e", f"APP_DATA_DIRECTORY={PLACEHOLDER}", "-e", f"NEXT_PUBLIC_FAST_API={PLACEHOLDER}",
        "-e", f"FAST_API_INTERNAL_URL={PLACEHOLDER}", "-e", f"USER_CONFIG_PATH={PLACEHOLDER}",
        "-e", f"DISABLE_AUTH={PLACEHOLDER}",
        "-e", "DATABASE_URL=postgres://presenton:pg-secret@presenton-relax-pg:5432/presenton",
        "-e", "MIGRATE_DATABASE_ON_STARTUP=true",
        "-e", "STORAGE_API_KEY=sk_rd_e2e",
        "-e", f"STORAGE_API_BASE_URL=http://{FAKE_CONTAINER}:9000/storage",
        "-e", "MEM0_ENABLED=false", "-e", "DISABLE_IMAGE_GENERATION=true", "-e", "WEB_GROUNDING=false",
        "-e", "LLM=custom", "-e", f"CUSTOM_LLM_URL=http://{FAKE_CONTAINER}:9000/v1",
        "-e", "CUSTOM_MODEL=fake-model", "-e", "CUSTOM_LLM_API_KEY=e2e-test",
        IMAGE,
    )
    for _ in range(100):
        try:
            if requests.get(f"{BASE}/api/v1/auth/status", timeout=3).status_code == 200:
                return started
        except requests.RequestException:
            pass
        time.sleep(1.5)
    print(docker("logs", "--tail", "60", APP, check_result=False))
    sys.exit("Presenton did not answer on port 8080")


DEPLOYS = [0]


def redeploy(grace: int = 30) -> float:
    docker("stop", "-t", str(grace), APP)
    DEPLOYS[0] += 1
    os.makedirs(os.path.join(HERE, ".relax-logs"), exist_ok=True)
    with open(os.path.join(HERE, ".relax-logs", f"deploy-{DEPLOYS[0]}.log"), "w", encoding="utf-8") as handle:
        handle.write(container_logs())
    return start_app()


def login(creds: dict) -> requests.Session:
    session = requests.Session()
    response = session.post(f"{BASE}/api/v1/auth/login", json=creds, timeout=30)
    if response.status_code != 200:
        sys.exit(f"login {creds['username']}: {response.status_code} {response.text[:200]}")
    return session


def admin_session() -> requests.Session:
    return login(ADMIN)


def storage() -> dict[str, int]:
    return requests.get(f"{FAKE}/storage/test/dump", timeout=10).json()


def wait_for(predicate, seconds: float = 20.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.5)
    return False


def upload(session: requests.Session, name: str, content: bytes) -> str:
    response = session.post(f"{BASE}/api/v1/ppt/images/upload", files={"file": (name, content, "image/png")}, timeout=30)
    if response.status_code != 200:
        sys.exit(f"upload {name}: {response.status_code} {response.text[:200]}")
    body = response.json()
    url = body.get("file_url") or ""
    return url[url.index("/app_data/"):] if "/app_data/" in url else url


def stored_name_for(app_url: str) -> str | None:
    tail = app_url.split("/app_data/", 1)[1]
    folder, name = tail.rsplit("/", 1)
    for key in storage():
        if f"/app_data/{folder}/" in key and key.endswith(f"-{name}"):
            return key
    return None


def main() -> int:
    start_infrastructure()
    fake(storage="ok", reset_log=True)
    start_app()
    check("placeholder variables are ignored", "Ignoring placeholder values of" in container_logs())

    requests.post(f"{BASE}/api/v1/auth/setup", json=ADMIN, timeout=30)
    admin = login(ADMIN)
    check("admin creates a user", admin.post(f"{BASE}/api/v1/admin/users", json=USER, timeout=30).status_code in (200, 201))
    user = login(USER)
    balance_before = user.get(f"{BASE}/api/v1/billing/me", timeout=30).json().get("balance")
    check("the user has the signup bonus", balance_before == 100, str(balance_before))

    first_png = png(text="first")
    first = upload(user, "first.png", first_png)
    check("uploaded image is served on port 8080", user.get(f"{BASE}{first}", timeout=30).content == first_png, first)
    check("the image is copied to the storage under its own name (no WebP)",
          wait_for(lambda: stored_name_for(first) is not None), str(storage()))
    check("signed out: the image is not served", requests.get(f"{BASE}{first}", timeout=30).status_code != 200)
    check("the SQLite file is not copied", not any(key.endswith("fastapi.db") for key in storage()))

    # Written right before the stop: the graceful shutdown must take it.
    second_png = png(text="second", color=(200, 40, 40))
    second = upload(user, "second.png", second_png)
    stopped = time.time()
    redeploy()
    check("a file written just before the stop is copied on shutdown", stored_name_for(second) is not None,
          f"stopped {time.time() - stopped:.1f}s ago; {storage()}")

    # New container, empty disk.
    status = user.get(f"{BASE}/api/v1/auth/status", timeout=30).json()
    check("signed-in users stay signed in (session secret restored)", status.get("authenticated") is True, str(status))
    user = login(USER)
    check("users survive the redeploy (PostgreSQL)", True)
    # Exports open the presentation at http://127.0.0.1 (port 80) inside the container.
    exported = admin_session().post(
        f"{BASE}/api/v1/ppt/presentation/generate",
        json={"content": "Экспорт", "n_slides": 2, "language": "Russian", "export_as": "pptx"},
        timeout=900,
    )
    path = exported.json().get("path", "") if exported.ok else ""
    download = admin_session().get(BASE + path[path.find("/app_data/"):], timeout=60) if "/app_data/" in path else None
    check("a presentation exports to PPTX", bool(download and download.ok and download.content[:2] == b"PK"),
          f"{exported.status_code} {exported.text[:200]}")
    check("balance survives the redeploy",
          user.get(f"{BASE}/api/v1/billing/me", timeout=30).json().get("balance") == balance_before)
    check("first image is back", user.get(f"{BASE}{first}", timeout=30).content == first_png)
    check("second image is back", user.get(f"{BASE}{second}", timeout=30).content == second_png)
    other = login(ADMIN)
    check("another account does not get it after the restore either",
          other.get(f"{BASE}{first}", timeout=30).status_code != 200)
    check("signed out after the redeploy: still not served", requests.get(f"{BASE}{first}", timeout=30).status_code != 200)
    uploads_before = len([e for e in fake_log() if e.get("kind") == "storage_upload" and "/images/" in e.get("key", "")])
    time.sleep(6)
    uploads_after = len([e for e in fake_log() if e.get("kind") == "storage_upload" and "/images/" in e.get("key", "")])
    check("restored files are not uploaded again", uploads_after == uploads_before, f"{uploads_before} -> {uploads_after}")

    # The CDN is down during the next deploy: the fallback link is used.
    fake(storage="cdn_down")
    redeploy()
    user = login(USER)
    check("CDN down: files come from the fallback link", user.get(f"{BASE}{first}", timeout=30).content == first_png)
    fake(storage="ok")

    # The whole storage is down during a deploy: the app works, files come back later.
    fake(storage="down")
    redeploy()
    user = login(USER)
    check("storage down: the app still starts and signs in", user.get(f"{BASE}/api/v1/auth/status", timeout=30).json().get("authenticated") is True)
    check("storage down: the missing image is a 404, not a 500",
          user.get(f"{BASE}{second}", timeout=30).status_code == 404)
    fake(storage="ok")
    check("storage back: the image is restored by the background retry (about a minute)",
          wait_for(lambda: user.get(f"{BASE}{second}", timeout=30).status_code == 200, seconds=90))

    # Deleting a file deletes its copy.
    key = stored_name_for(first)
    docker("exec", APP, "sh", "-c", "rm -f /app_data" + first[len("/app_data"):])
    check("a file deleted on the disk is deleted in the storage", wait_for(lambda: key not in storage()))

    deletes = [e["key"] for e in fake_log() if e.get("kind") == "storage_delete" and "/images/" in e["key"]]
    check("no image copy was deleted except the one deleted on purpose", deletes == [key], str(deletes))
    check("the other image is still in the storage", stored_name_for(second) is not None)

    errors = [line for line in container_logs().splitlines() if "Traceback" in line]
    check("no tracebacks in the log", not errors, "\n".join(errors[:5]))
    return summary()


if __name__ == "__main__":
    sys.exit(main())
