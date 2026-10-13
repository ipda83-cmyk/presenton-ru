"""Roles, page guards and locales on the e2e stand."""

import sys

import requests

from common import BASE, check, data_url, login, png, summary

user = login("user")
admin = login("admin")
user_en = login("user", locale="en")
anon = requests.Session()

# Pages are an app shell for everyone; the client shows the login form (see anon.cjs)
# and every data API answers 401 without a session.
for path in ["/studio", "/studio/brush", "/studio/reference", "/studio/storyboard", "/upload", "/dashboard"]:
    r = user.get(BASE + path, timeout=60)
    check(f"user {path} -> 200", r.status_code == 200, f"{r.status_code}")
for path in ["/api/v1/studio/history", "/api/v1/ppt/presentation/all", "/api/v1/ppt/images/uploaded"]:
    r = anon.get(BASE + path, timeout=30)
    check(f"anon {path} -> 401", r.status_code == 401, f"{r.status_code}")

# admin-only API
for method, path, body in [
    ("get", "/api/v1/admin/users", None),
    ("get", "/api/v1/admin/provider-settings", None),
    ("put", "/api/v1/admin/provider-settings", {"STUDIO_API_KEY": "stolen"}),
    ("post", "/api/v1/admin/users", {"username": "evil", "password": "evilpassword1"}),
]:
    r = getattr(user, method)(BASE + path, json=body, timeout=30)
    check(f"user {method.upper()} {path} -> 403", r.status_code == 403, f"{r.status_code} {r.text[:120]}")
r = admin.get(BASE + "/api/v1/admin/provider-settings", timeout=30)
check("admin reads provider settings (keys are shown to admins, as for every provider)", r.status_code == 200, f"{r.status_code}")
cfg = user.get(BASE + "/api/v1/studio/config", timeout=30).json()
check("studio config for users has no key", "key" not in str(cfg).lower() or "e2e-test" not in str(cfg), str(cfg)[:200])

# the same error in both languages
body = {"image": data_url(png()), "prompt": "", "model": "nano_banana_2"}
ru = user.post(BASE + "/api/v1/studio/edit", json=body, timeout=30).json()["detail"]
en = user_en.post(BASE + "/api/v1/studio/edit", json=body, timeout=30).json()["detail"]
check("RU error text", ru == "Опишите, что изменить.", ru)
check("EN error text", en.startswith("Describe"), en)
r = user_en.post(BASE + "/api/v1/studio/storyboard", json={"image": data_url(png()), "view": "front", "model": "chatgpt_images_2"}, timeout=30)
check("EN storyboard model error", r.status_code == 400 and "Gemini" in r.json()["detail"] and not any("Ѐ" <= c <= "ӿ" for c in r.json()["detail"]), r.text[:200])
r = requests.post(BASE + "/api/v1/studio/generate", json={"prompt": "x"}, headers={"Accept-Language": "zh-CN,zh;q=0.9"}, timeout=30)
check("unknown Accept-Language, no session -> 401, not 500", r.status_code == 401, f"{r.status_code}")
s = login("user")
s.cookies.set("NEXT_LOCALE", "xx-<script>")
r = s.post(BASE + "/api/v1/studio/generate", json={"prompt": "x", "model": "nope"}, timeout=30)
check("broken locale cookie -> normal 400", r.status_code == 400 and "<script>" not in r.text, f"{r.status_code} {r.text[:120]}")

sys.exit(summary())
