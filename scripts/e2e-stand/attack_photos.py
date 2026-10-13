"""Attack the slide-photo endpoints on the e2e stand."""

import sys
import uuid

import requests

from common import BASE, check, fake, fake_log, login, png, summary

P = f"{BASE}/api/v1/ppt"
fake(llm="ok", arckep="ok", reset_log=True)
user = login("user")
admin = login("admin")
anon = requests.Session()


def upload(session, name, color):
    r = session.post(f"{P}/images/upload", files={"file": (name, png((800, 600), color, name), "image/png")}, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("file_url") or body.get("path")


r = user.post(f"{P}/presentation/create", json={"content": "Солнечные панели для офиса: экономия, монтаж, окупаемость", "n_slides": 5, "language": "Russian"}, timeout=60)
check("create presentation -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
pid = r.json()["id"]
mine = [upload(user, f"photo-{i}.png", (30 * i, 100, 160)) for i in range(1, 4)]
theirs = upload(admin, "admin-secret.png", (200, 20, 20))
check("uploaded photos are /app_data urls", all(u.startswith("/app_data/") for u in mine), str(mine))

# auth / ownership
check("anon GET photos -> 401", anon.get(f"{P}/outlines/{pid}/photos", timeout=30).status_code == 401)
for method, path, body in [("get", "/photos", None), ("put", "/photos", {"photos": []}), ("post", "/photos/match", {})]:
    r = getattr(admin, method)(f"{P}/outlines/{pid}{path}", json=body, timeout=30)
    check(f"other user {method.upper()} {path} -> 404", r.status_code == 404, f"{r.status_code} {r.text[:120]}")
r = user.get(f"{P}/outlines/{uuid.uuid4()}/photos", timeout=30)
check("unknown presentation -> 404", r.status_code == 404, f"{r.status_code}")
check("bad uuid -> 422", user.get(f"{P}/outlines/nope/photos", timeout=30).status_code == 422)

# normalisation
hostile = [
    {"url": mine[0], "name": "  первое \n фото  ", "slide": 0},
    {"url": mine[0], "name": "duplicate"},
    {"url": "/etc/passwd"},
    {"url": "/app_data/../etc/passwd"},
    {"url": "/app_data/images/../../etc/passwd"},
    {"url": theirs, "name": "чужое"},
    {"url": "http://evil.example/x.png"},
    {"url": "/static/images/placeholder.jpg"},
    {"url": mine[1]},
    {"url": mine[2], "slide": 10 ** 9, "name": "x" * 100},
]
for name, item in [("negative slide", {"url": mine[1], "slide": -3}), ("name 500 chars", {"url": mine[1], "name": "x" * 500})]:
    r = user.put(f"{P}/outlines/{pid}/photos", json={"photos": [item]}, timeout=30)
    check(f"PUT {name} -> 422", r.status_code == 422, f"{r.status_code}")
r = user.put(f"{P}/outlines/{pid}/photos", json={"photos": hostile}, timeout=30)
ok = check("PUT hostile photo list -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
if ok:
    urls = [p["url"] for p in r.json()["photos"]]
    check("only the user's own photos survive, deduplicated", urls == mine, str(urls))
    check("other user's image is dropped", theirs not in urls)
    check("name whitespace is collapsed", r.json()["photos"][0]["name"] == "первое фото", str(r.json()["photos"][0]))
    check("huge slide index is kept for alignment (ignored at generation)", r.json()["photos"][2]["slide"] == 10 ** 9, str(r.json()["photos"][2]))
r = user.put(f"{P}/outlines/{pid}/photos", json={"photos": [{"url": mine[0]}] * 21}, timeout=30)
check("21 photos -> 422", r.status_code == 422, f"{r.status_code}")
r = user.put(f"{P}/outlines/{pid}/photos", json={"photos": [{"url": mine[0], "slide": "abc"}]}, timeout=30)
check("slide as text -> 422 or null", r.status_code == 422 or r.json()["photos"][0]["slide"] is None, f"{r.status_code} {r.text[:120]}")
r = user.put(f"{P}/outlines/{pid}/photos", json={"photos": [{"url": u} for u in mine], "matched": "telepathy"}, timeout=30)
check("unknown matched method -> 422", r.status_code == 422, f"{r.status_code}")
r = user.put(f"{P}/outlines/{pid}/photos", json={"photos": [{"url": u} for u in mine]}, timeout=30)
check("PUT clean list -> 200", r.status_code == 200)

# matching before the outline exists
r = user.post(f"{P}/outlines/{pid}/photos/match", json={}, timeout=120)
check("match before the outline exists -> no 500", r.status_code < 500, f"{r.status_code} {r.text[:200]}")

slides = [{"content": f"## Слайд {i}\nТекст про солнечные панели {i}"} for i in range(1, 6)]
fake(reset_log=True)
r = user.post(f"{P}/outlines/{pid}/photos/match", json={"slides": slides}, timeout=120)
ok = check("match with outline (fake vision model) -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
if ok:
    body = r.json()
    check("every photo got a slide or null, within range", all(p["slide"] is None or 0 <= p["slide"] < 5 for p in body["photos"]), str(body["photos"]))
    sent = [e for e in fake_log() if e["kind"] == "llm"]
    check(f"match method reported ({body['matched']})", body["matched"] in ("vision", "order"), str(body))
    if body["matched"] == "vision":
        check("vision call carried the images", any(e["images"] for e in sent), str(sent)[:200])

for mode in ("http500", "garbage", "empty"):
    fake(llm=mode)
    r = user.post(f"{P}/outlines/{pid}/photos/match", json={"slides": slides}, timeout=180)
    check(f"match with LLM {mode} -> falls back to order", r.status_code == 200 and r.json()["matched"] == "order", f"{r.status_code} {r.text[:200]}")
fake(llm="ok")
r = user.post(f"{P}/outlines/{pid}/photos/match", json={"slides": []}, timeout=60)
check("match with zero slides -> no 500", r.status_code < 500, f"{r.status_code} {r.text[:200]}")

r = user.get(f"{P}/outlines/{pid}/photos", timeout=30)
check("GET photos returns the saved record", r.status_code == 200 and len(r.json()["photos"]) == 3, r.text[:200])

sys.exit(summary())
