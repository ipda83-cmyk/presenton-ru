"""Accounts for the attacks: an administrator, a user with plenty of money for the
Studio/photo attacks, and a payer that starts with only the signup bonus."""

import requests

from common import BASE, accounts, login

creds = accounts()
status = requests.get(f"{BASE}/api/v1/auth/status", timeout=10).json()
if not status["configured"]:
    r = requests.post(f"{BASE}/api/v1/auth/setup", json=creds["admin"], timeout=30)
    print("setup", r.status_code, r.text[:200])
admin = login("admin")
for role in ("user", "payer"):
    r = admin.post(f"{BASE}/api/v1/admin/users", json=creds[role], timeout=30)
    print("create", role, r.status_code)
ids = {row["username"]: row["user_id"] for row in admin.get(f"{BASE}/api/v1/admin/billing/accounts", timeout=30).json()["accounts"]}
r = admin.post(
    f"{BASE}/api/v1/admin/billing/adjust",
    json={"user_id": ids[creds["user"]["username"]], "amount": 100000, "mode": "set", "note": "e2e attacks"},
    timeout=30,
)
print("user balance", r.json().get("balance"))
