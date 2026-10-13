import requests

from common import BASE, accounts, login

creds = accounts()
status = requests.get(f"{BASE}/api/v1/auth/status", timeout=10).json()
if not status["configured"]:
    r = requests.post(f"{BASE}/api/v1/auth/setup", json=creds["admin"], timeout=30)
    print("setup", r.status_code, r.text[:200])
admin = login("admin")
r = admin.post(f"{BASE}/api/v1/admin/users", json=creds["user"], timeout=30)
print("create user", r.status_code, r.text[:160])
user = login("user")
print("user status", user.get(f"{BASE}/api/v1/auth/status").json())
