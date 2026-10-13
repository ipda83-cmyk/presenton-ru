"""Shared helpers for the e2e attack scripts (stand on 127.0.0.1:5057, fake upstream on :9056)."""

import base64
import io
import json
import os
import secrets
import sys

import requests
from PIL import Image, ImageDraw

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:5057")
FAKE = os.environ.get("E2E_FAKE", "http://127.0.0.1:9056")
HERE = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS = os.path.join(HERE, "accounts.json")

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)
    return ok


def summary() -> int:
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    for name, _, detail in failed:
        print("  FAILED:", name, "--", detail[:300])
    return 1 if failed else 0


def fake(**state) -> dict:
    return requests.post(f"{FAKE}/control", json=state, timeout=10).json()


def fake_log() -> list[dict]:
    return requests.get(f"{FAKE}/control", timeout=10).json()["log"]


def accounts() -> dict:
    if os.path.exists(ACCOUNTS):
        with open(ACCOUNTS, encoding="utf-8") as f:
            data = json.load(f)
        if "payer" in data:
            return data
        data["payer"] = {"username": "e2e-payer", "password": secrets.token_urlsafe(12)}
        with open(ACCOUNTS, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data
    data = {
        "admin": {"username": "e2e-admin", "password": secrets.token_urlsafe(12)},
        "user": {"username": "e2e-user", "password": secrets.token_urlsafe(12)},
        "payer": {"username": "e2e-payer", "password": secrets.token_urlsafe(12)},
    }
    with open(ACCOUNTS, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def login(role: str, locale: str = "ru") -> requests.Session:
    creds = accounts()[role]
    session = requests.Session()
    session.cookies.set("NEXT_LOCALE", locale)
    response = session.post(f"{BASE}/api/v1/auth/login", json=creds, timeout=30)
    if response.status_code != 200:
        sys.exit(f"login {role} failed: {response.status_code} {response.text[:200]}")
    return session


def png(size=(640, 480), color=(40, 120, 200), text="") -> bytes:
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4), fill=(240, 200, 60))
    if text:
        draw.text((10, 10), text, fill=(255, 255, 255))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def data_url(data: bytes, mime="image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def mask_png(size=(640, 480)) -> bytes:
    """Transparent square in the middle = area to change."""
    image = Image.new("RGBA", size, (0, 0, 0, 255))
    ImageDraw.Draw(image).rectangle((size[0] // 3, size[1] // 3, size[0] * 2 // 3, size[1] * 2 // 3), fill=(0, 0, 0, 0))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()
