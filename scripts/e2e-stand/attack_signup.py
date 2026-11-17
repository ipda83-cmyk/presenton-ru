"""Self sign-up on a separate stand: closed by default, captcha, consent,
disposable mail, per-IP limit, confirmation letter and bonus, password reset,
public documents.

    python scripts/e2e-stand/attack_signup.py

Presenton: http://127.0.0.1:5061 (container presenton-signup); the fake
upstream (LLM, SMTP on :2525, SmartCaptcha) is shared with the other stands.
"""

import os
import re
import subprocess
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
os.environ.setdefault("E2E_BASE", "http://127.0.0.1:5061")
sys.path.insert(0, HERE)

from common import BASE, check, fake, fake_log, summary  # noqa: E402

IMAGE = os.environ.get("PRESENTON_IMAGE", "presenton-ru-production:latest")
NETWORK = "presenton-e2e"
APP = "presenton-signup"
FAKE_CONTAINER = "presenton-e2e-fake"
ADMIN = {"username": "signup-admin", "password": "signup-admin-pass-1"}
A = f"{BASE}/api/v1/auth"


def docker(*args: str, check_result: bool = True) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check_result and result.returncode != 0:
        sys.exit(f"docker {' '.join(args[:3])}: {result.stderr.strip()[:400]}")
    return result.stdout


def start() -> None:
    docker("network", "create", NETWORK, check_result=False)
    docker("rm", "-f", FAKE_CONTAINER, APP, check_result=False)
    docker("run", "-d", "--name", FAKE_CONTAINER, "--network", NETWORK, "-p", "127.0.0.1:9056:9000",
           "-v", f"{HERE}:/e2e", "--entrypoint", "/opt/venv/bin/python", IMAGE, "/e2e/fake_upstream.py")
    docker(
        "run", "-d", "--name", APP, "--network", NETWORK, "-p", "127.0.0.1:5061:80",
        "-v", f"{os.path.join(ROOT, 'servers', 'fastapi')}:/app/servers/fastapi",
        "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "MEM0_ENABLED=false", "-e", "WEB_GROUNDING=false",
        "-e", "LLM=custom", "-e", f"CUSTOM_LLM_URL=http://{FAKE_CONTAINER}:9000/v1",
        "-e", "CUSTOM_MODEL=fake-model", "-e", "CUSTOM_LLM_API_KEY=e2e-test",
        "-e", "IMAGE_PROVIDER=pexels", "-e", "PEXELS_API_KEY=unused", "-e", "PRESENTON_COMMUNITY_ENABLED=false",
        "-e", f"SMTP_HOST={FAKE_CONTAINER}", "-e", "SMTP_PORT=2525", "-e", "SMTP_SECURITY=none",
        "-e", "SMTP_FROM=noreply@kvant.test", "-e", "PRESENTON_PUBLIC_URL=http://127.0.0.1:5061",
        "-e", "SMARTCAPTCHA_CLIENT_KEY=e2e-client", "-e", "SMARTCAPTCHA_SERVER_KEY=e2e-server",
        "-e", f"SMARTCAPTCHA_VALIDATE_URL=http://{FAKE_CONTAINER}:9000/smartcaptcha/validate",
        IMAGE,
    )
    for _ in range(100):
        try:
            if requests.get(f"{A}/status", timeout=3).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1.5)
    sys.exit("Presenton did not start")


def browser(ip: str = "77.88.55.60") -> requests.Session:
    session = requests.Session()
    session.cookies.set("NEXT_LOCALE", "ru")
    session.headers["X-Forwarded-For"] = ip
    return session


def signup(session: requests.Session, email: str, **extra) -> requests.Response:
    body = {"email": email, "password": "user-pass-123", "accept_offer": True, "accept_privacy": True, "captcha": "good-token", **extra}
    return session.post(f"{A}/register", json=body, timeout=60)


def letters_to(address: str) -> list[dict]:
    return [entry for entry in fake_log() if entry.get("kind") == "mail" and address in entry.get("to", [])]


def link_token(letter: dict, path: str) -> str:
    match = re.search(rf"{path}\?token=([\w.\-]+)", letter.get("text", ""))
    return match.group(1) if match else ""


def balance(session: requests.Session) -> int:
    return session.get(f"{BASE}/api/v1/billing/me", timeout=60).json().get("balance", -1)


def main() -> int:
    start()
    fake(reset_log=True)
    requests.post(f"{A}/setup", json=ADMIN, timeout=30)
    admin = browser("5.45.192.10")
    admin.post(f"{A}/login", json=ADMIN, timeout=30)

    # Closed by default.
    anna = browser()
    check("sign-up is closed until opened", anna.get(f"{A}/registration", timeout=30).json()["open"] is False)
    check("a closed sign-up refuses", signup(anna, "anna@example.com").status_code == 403)
    r = anna.put(f"{BASE}/api/v1/admin/registration", json={"open": True}, timeout=30)
    check("users cannot open it", r.status_code in (401, 403), str(r.status_code))
    state = admin.put(f"{BASE}/api/v1/admin/registration", json={"open": True, "ip_daily_limit": 3}, timeout=30).json()
    check("the administrator opens it (mail and captcha ready)", state["settings"]["open"] and state["mail"]["configured"] and state["captcha"]["configured"], str(state))
    test = admin.post(f"{BASE}/api/v1/admin/registration/test-email", json={"to": "owner@example.com"}, timeout=60)
    check("a test letter goes out", test.status_code == 200 and letters_to("owner@example.com"), test.text[:200])

    # Checks before an account is created.
    check("no captcha: refused", signup(anna, "anna@example.com", captcha=None).status_code == 400)
    check("wrong captcha: refused", signup(anna, "anna@example.com", captcha="bot").status_code == 400)
    check("no consent: refused", signup(anna, "anna@example.com", accept_offer=False).status_code == 422)
    check("disposable mail: refused", signup(anna, "anna@mailinator.com").status_code == 422)

    # Sign-up: signed in, letter sent, no bonus yet.
    r = signup(anna, "Anna@Example.com")
    check("a user signs up and is signed in", r.status_code == 200 and anna.get(f"{A}/status", timeout=30).json()["authenticated"], r.text[:200])
    status = anna.get(f"{A}/status", timeout=30).json()
    check("the e-mail is not confirmed yet", status["verified"] is False and status["username"] == "anna@example.com", str(status))
    check("no bonus before confirmation", balance(anna) == 0, str(balance(anna)))
    letters = letters_to("anna@example.com")
    check("a confirmation letter arrives", letters and "Подтвердите" in letters[-1]["subject"], str(letters[-1:]))
    check("its link points to the public address", "http://127.0.0.1:5061/verify-email?token=" in (letters[-1]["text"] if letters else ""))
    check("the same address cannot sign up twice", signup(browser("5.45.192.11"), "anna@example.com").status_code == 409)

    # Resend is limited.
    resent = [anna.post(f"{A}/verify-email/resend", timeout=60).status_code for _ in range(4)]
    check("resending is limited", resent[:3] == [200, 200, 200] and resent[3] == 429, str(resent))

    # Confirmation: the bonus once.
    token = link_token(letters_to("anna@example.com")[-1], "/verify-email")
    first = requests.post(f"{A}/verify-email", json={"token": token}, timeout=30).json()
    second = requests.post(f"{A}/verify-email", json={"token": token}, timeout=30).json()
    check("confirmation gives the bonus once", first.get("bonus") == 100 and second.get("bonus") == 0, f"{first} {second}")
    check("the balance has the bonus", balance(anna) == 100, str(balance(anna)))
    check("the e-mail is confirmed", anna.get(f"{A}/status", timeout=30).json()["verified"] is True)

    # Per-IP limit.
    crowd = browser("77.88.55.61")
    codes = [signup(crowd, f"crowd{index}@example.com").status_code for index in range(4)]
    check("sign-ups from one address are limited", codes == [200, 200, 200, 429], str(codes))

    # Password reset.
    before = len(letters_to("anna@example.com"))
    r = browser("5.45.192.12").post(f"{A}/password/forgot", json={"email": "anna@example.com"}, timeout=60)
    check("a reset letter is sent", r.status_code == 200 and len(letters_to("anna@example.com")) == before + 1, r.text[:200])
    unknown = browser("5.45.192.12").post(f"{A}/password/forgot", json={"email": "ghost@example.com"}, timeout=60)
    check("unknown addresses get the same answer", unknown.status_code == 200 and not letters_to("ghost@example.com"))
    reset_token = link_token(letters_to("anna@example.com")[-1], "/reset-password")
    fresh = browser("5.45.192.13")
    r = fresh.post(f"{A}/password/reset", json={"token": reset_token, "password": "new-pass-456"}, timeout=30)
    check("the password is reset and the user signed in", r.status_code == 200 and fresh.get(f"{A}/status", timeout=30).json()["authenticated"], r.text[:200])
    check("the old session is closed", anna.get(f"{A}/status", timeout=30).json()["authenticated"] is False)
    again = fresh.post(f"{A}/password/reset", json={"token": reset_token, "password": "other-pass-789"}, timeout=30)
    check("the reset link works once", again.status_code == 400, str(again.status_code))
    login = browser().post(f"{A}/login", json={"username": "anna@example.com", "password": "new-pass-456"}, timeout=30)
    check("signing in with the new password works", login.status_code == 200, login.text[:200])

    # Documents.
    saved = admin.put(f"{BASE}/api/v1/admin/legal/offer", json={"title": "Договор-оферта", "body": "## 1. Термины\nТекст оферты."}, timeout=30)
    check("the administrator publishes the offer", saved.status_code == 200, saved.text[:200])
    public = requests.get(f"{BASE}/api/v1/legal/offer", timeout=30)
    check("the offer is readable without signing in", public.status_code == 200 and public.json()["title"] == "Договор-оферта")
    page = requests.get(f"{BASE}/legal/offer", timeout=60)
    check("the offer page opens without signing in", page.status_code == 200 and "Договор-оферта" in page.text, str(page.status_code))
    check("the sign-up page opens without signing in", requests.get(f"{BASE}/register", timeout=60).status_code == 200)
    check("sign-up links to the offer", anna.get(f"{A}/registration", timeout=30).json()["offer_url"] == "/legal/offer")
    r = anna.put(f"{BASE}/api/v1/admin/legal/offer", json={"title": "x", "body": "y"}, timeout=30)
    check("users cannot edit documents", r.status_code in (401, 403), str(r.status_code))

    logs = subprocess.run(["docker", "logs", APP], capture_output=True, text=True, encoding="utf-8", errors="replace")
    errors = [line for line in (logs.stdout + logs.stderr).splitlines() if "Traceback" in line]
    check("no tracebacks", not errors, "\n".join(errors[:3]))
    return summary()


if __name__ == "__main__":
    sys.exit(main())
