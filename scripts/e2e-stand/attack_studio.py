"""Attack the Studio API on the e2e stand. Usage: python attack_studio.py [--slow]

Stops and restarts the fake upstream container once (arckep unreachable).
"""

import base64
import concurrent.futures
import io
import sys
import time

import requests
from PIL import Image

from common import BASE, check, data_url, fake, fake_log, login, mask_png, png, summary

S = f"{BASE}/api/v1/studio"
SLOW = "--slow" in sys.argv
fake(llm="ok", arckep="ok", reset_log=True)

user = login("user")
admin = login("admin")
anon = requests.Session()

# ---------------------------------------------------------------- auth
for method, path, body in [
    ("get", "/config", None), ("post", "/generate", {"prompt": "x"}), ("post", "/edit", {"image": "x", "prompt": "x"}),
    ("post", "/storyboard", {"image": "x", "view": "front"}), ("get", "/history", None),
    ("delete", "/history/00000000-0000-0000-0000-000000000000", None),
]:
    r = getattr(anon, method)(S + path, json=body, timeout=30)
    check(f"anon {method.upper()} {path} -> 401", r.status_code == 401, f"{r.status_code} {r.text[:120]}")
forged = requests.Session()
forged.cookies.set("presenton_session", "forged.value.here")
r = forged.get(S + "/history", timeout=30)
check("forged cookie -> 401", r.status_code == 401, f"{r.status_code}")

# ---------------------------------------------------------------- config
cfg = user.get(S + "/config", timeout=30).json()
check("config configured with fake key", cfg["configured"] is True, str(cfg)[:200])
check("config lists 12 storyboard views", len(cfg["storyboard_views"]) == 12)
models = {m["key"]: m for m in cfg["models"]}
gemini = next(k for k, m in models.items() if m["family"] == "gemini")
gpt = next(k for k, m in models.items() if m["family"] == "gpt")

# ---------------------------------------------------------------- generate: input
for name, body, expect in [
    ("empty prompt", {"prompt": ""}, 422),
    ("prompt 4001 chars", {"prompt": "a" * 4001}, 422),
    ("count 0", {"prompt": "cat", "count": 0}, 422),
    ("count 5", {"prompt": "cat", "count": 5}, 422),
    ("unknown model", {"prompt": "cat", "model": "dall-e-9"}, 400),
    ("prompt is a number", {"prompt": 12345}, 422),
]:
    r = user.post(S + "/generate", json=body, timeout=30)
    check(f"generate {name} -> {expect}", r.status_code == expect, f"{r.status_code} {r.text[:160]}")
r = user.post(S + "/generate", data="{not json", headers={"Content-Type": "application/json"}, timeout=30)
check("generate invalid JSON -> 422", r.status_code == 422, f"{r.status_code}")
r = user.post(S + "/generate", json={"prompt": "cat", "model": "dall-e-9"}, timeout=30)
check("unknown model error is in Russian", any("Ѐ" <= ch <= "ӿ" for ch in r.text), r.text[:160])

# ---------------------------------------------------------------- generate: happy path
r = user.post(S + "/generate", json={"prompt": "Кот в шляпе 🎩 на фоне гор", "model": gpt, "count": 2, "quality": "draft"}, timeout=120)
ok = check("generate emoji/cyrillic prompt, count 2 -> 200 with 2 images", r.status_code == 200 and len(r.json().get("images", [])) == 2, f"{r.status_code} {r.text[:200]}")
user_image = r.json()["images"][0] if ok else None
if user_image:
    img = user.get(BASE + user_image["file_url"], timeout=30)
    check("generated file is served to its owner", img.status_code == 200 and img.content[:4] == b"\x89PNG", f"{img.status_code}")
    other = admin.get(BASE + user_image["file_url"], timeout=30)
    check("another user cannot fetch the owner's file", other.status_code in (403, 404), f"{other.status_code}")
    check("anon cannot fetch the file", anon.get(BASE + user_image["file_url"], timeout=30).status_code in (401, 403, 404))

# ---------------------------------------------------------------- ownership
hist_user = user.get(S + "/history", timeout=30).json()["images"]
hist_admin = admin.get(S + "/history", timeout=30).json()["images"]
check("history has the user's images", user_image and any(i["id"] == user_image["id"] for i in hist_user))
check("other user's history does not show them", user_image and not any(i["id"] == user_image["id"] for i in hist_admin))
if user_image:
    r = admin.delete(S + f"/history/{user_image['id']}", timeout=30)
    check("other user cannot delete the image -> 404", r.status_code == 404, f"{r.status_code}")
    r = admin.post(S + "/edit", json={"image": user_image["file_url"], "prompt": "make it red", "model": gemini}, timeout=60)
    check("other user cannot edit by the owner's path -> 404", r.status_code == 404, f"{r.status_code} {r.text[:120]}")
    r = admin.post(S + "/storyboard", json={"image": user_image["file_url"], "view": "front", "model": gemini}, timeout=60)
    check("other user cannot storyboard the owner's path -> 404", r.status_code == 404, f"{r.status_code}")
r = user.delete(S + "/history/not-a-uuid", timeout=30)
check("delete with bad id -> 422", r.status_code == 422, f"{r.status_code}")

# ---------------------------------------------------------------- edit: inputs
src = png()
for name, image, expect in [
    ("path traversal", "/app_data/../etc/passwd", 404),
    ("absolute server path", "/etc/passwd", 404),
    ("file:// url", "file:///etc/passwd", 404),
    ("static traversal", "/static/../../etc/passwd", 404),
    ("loopback url", "http://127.0.0.1/api/v1/studio/config", 404),
    ("metadata url", "http://169.254.169.254/latest/meta-data/", 404),
    ("private docker host", "http://presenton-e2e-fake:9000/control", 404),
    ("localhost by name", "http://localhost:80/static/../etc/passwd", 404),
    ("data url not base64", "data:image/png,hello", 400),
    ("data url garbage", "data:image/png;base64,AAAA", 400),
    ("svg data url", data_url(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"), 400),
]:
    r = user.post(S + "/edit", json={"image": image, "prompt": "x", "model": gemini}, timeout=60)
    check(f"edit {name} -> {expect}", r.status_code == expect, f"{r.status_code} {r.text[:160]}")

r = user.post(S + "/edit", json={"image": data_url(src), "prompt": "   ", "model": gemini}, timeout=60)
check("edit blank prompt without operation -> 400", r.status_code == 400, f"{r.status_code}")
big = "data:image/png;base64," + "A" * (34 * 1024 * 1024)
r = user.post(S + "/edit", json={"image": big, "prompt": "x", "model": gemini}, timeout=120)
check("edit 34 MB data url -> 413", r.status_code == 413, f"{r.status_code} {r.text[:120]}")
bomb = Image.new("1", (12000, 12000))
buf = io.BytesIO()
bomb.save(buf, "PNG")
r = user.post(S + "/edit", json={"image": data_url(buf.getvalue()), "prompt": "x", "model": gemini}, timeout=60)
check(f"edit decompression bomb ({len(buf.getvalue())//1024} KB, 144 MP) -> 400", r.status_code == 400, f"{r.status_code} {r.text[:120]}")
r = user.post(S + "/edit", json={"image": data_url(src), "prompt": "x", "mask": "data:image/png;base64,AAAA", "model": gemini}, timeout=60)
check("edit garbage mask -> 400", r.status_code == 400, f"{r.status_code}")

# happy edits
r = user.post(S + "/edit", json={"image": data_url(src), "prompt": "добавь солнце", "model": gemini}, timeout=120)
check("edit by description -> 200", r.status_code == 200 and r.json()["image"]["extras"]["mode"] == "edit", f"{r.status_code} {r.text[:160]}")
r = user.post(S + "/edit", json={"image": data_url(src), "prompt": "красный круг", "mask": data_url(mask_png((300, 200))), "model": gemini}, timeout=120)
check("brush with mask of another size -> 200", r.status_code == 200 and r.json()["image"]["extras"]["mode"] == "brush", f"{r.status_code} {r.text[:160]}")
big_src = png((1600, 1200), (90, 140, 60))
small_mask = Image.new("RGBA", (1600, 1200), (0, 0, 0, 255))
from PIL import ImageDraw as _D
_D.Draw(small_mask).rectangle((760, 560, 840, 640), fill=(0, 0, 0, 0))
buf2 = io.BytesIO(); small_mask.save(buf2, "PNG")
r = user.post(S + "/edit", json={"image": data_url(big_src), "prompt": "красный круг", "mask": data_url(buf2.getvalue()), "model": gemini}, timeout=120)
if check("brush small area on a big photo -> 200", r.status_code == 200, f"{r.status_code} {r.text[:160]}"):
    out = Image.open(io.BytesIO(user.get(BASE + r.json()["image"]["file_url"]).content)).convert("RGB")
    orig = Image.open(io.BytesIO(big_src)).convert("RGB")
    check("brush keeps the original size", out.size == orig.size, f"{out.size}")
    check("brush keeps far pixels exact", out.getpixel((5, 5)) == orig.getpixel((5, 5)), f"{out.getpixel((5, 5))} vs {orig.getpixel((5, 5))}")
    near = (760 - 150, 600)  # in the soft edge: tone drift (+6 from the fake) must be undone
    diff = max(abs(a - b) for a, b in zip(out.getpixel(near), orig.getpixel(near)))
    check("brush edge has no tone halo (<=2 levels)", diff <= 2, f"{out.getpixel(near)} vs {orig.getpixel(near)}")
for op in ("upscale", "remove_bg"):
    r = user.post(S + "/edit", json={"image": data_url(src), "operation": op, "model": gemini}, timeout=120)
    check(f"operation {op} without prompt -> 200", r.status_code == 200 and r.json()["image"]["extras"]["mode"] == op, f"{r.status_code} {r.text[:160]}")
r = user.post(S + "/edit", json={"image": data_url(src), "operation": "explode", "model": gemini}, timeout=60)
check("unknown operation -> 422", r.status_code == 422, f"{r.status_code}")
r = user.post(S + "/edit", json={"image": data_url(src), "reference": data_url(png((200, 200), (200, 30, 30))), "mask": data_url(mask_png()), "model": gemini}, timeout=120)
check("reference insert without prompt -> 200", r.status_code == 200 and r.json()["image"]["extras"]["mode"] == "reference", f"{r.status_code} {r.text[:160]}")
if user_image:
    r = user.post(S + "/edit", json={"image": user_image["file_url"], "prompt": "ярче", "model": gpt, "quality": "draft"}, timeout=120)
    check("edit own history image on gpt -> 200 and parent recorded", r.status_code == 200 and r.json()["image"]["extras"].get("parent") == user_image["file_url"], f"{r.status_code} {r.text[:160]}")

# ---------------------------------------------------------------- storyboard
for name, body, expect in [
    ("unknown view", {"image": data_url(src), "view": "upside_down", "model": gemini}, 400),
    ("gpt model", {"image": data_url(src), "view": "front", "model": gpt}, 400),
    ("details 1001", {"image": data_url(src), "view": "front", "model": gemini, "details": "a" * 1001}, 422),
    ("no image", {"view": "front", "model": gemini}, 422),
    ("view 65 chars", {"image": data_url(src), "view": "v" * 65, "model": gemini}, 422),
]:
    r = user.post(S + "/storyboard", json=body, timeout=60)
    check(f"storyboard {name} -> {expect}", r.status_code == expect, f"{r.status_code} {r.text[:160]}")
r = user.post(S + "/storyboard", json={"image": data_url(src), "view": " profile_left ", "model": gemini, "details": "в каске\n\nи очках"}, timeout=120)
ok = check("storyboard view with spaces + multiline details -> 200", r.status_code == 200 and r.json()["image"]["extras"]["view"] == "profile_left", f"{r.status_code} {r.text[:160]}")
if ok:
    job = [e for e in fake_log() if e["kind"] == "job"][-1]
    check("storyboard prompt carries view + details", "left side profile" in job["prompt"] and job["refs"] == 1, str(job)[:200])

# ---------------------------------------------------------------- upstream faults
for mode, expect in [("create500", 502), ("create429", 429), ("balance", 503), ("scope", 502), ("job_failed", 502),
                     ("garbage", 502), ("bad_image", 502), ("download404", 502), ("upload500", 502)]:
    fake(arckep=mode)
    t0 = time.time()
    r = user.post(S + "/edit", json={"image": data_url(src), "prompt": "x", "model": gemini}, timeout=200)
    body = r.text
    check(f"arckep {mode} -> {expect} with a readable message", r.status_code == expect and "detail" in r.json(), f"{r.status_code} {body[:200]} ({time.time()-t0:.0f}s)")
fake(arckep="ok")

# ---------------------------------------------------------------- concurrency: shared 5-job limit
fake(reset_log=True)
def one(i):
    return user.post(S + "/storyboard", json={"image": data_url(src), "view": "front", "model": gemini}, timeout=200).status_code
with concurrent.futures.ThreadPoolExecutor(8) as pool:
    codes = list(pool.map(one, range(8)))
state = fake()["state"]
check("8 parallel storyboard views (two tabs) all succeed", codes.count(200) == 8, f"codes={codes} max_active={state['max_active_jobs']}")
check("never more than 5 arckep jobs at once", state["max_active_jobs"] <= 5, str(state["max_active_jobs"]))

import subprocess
subprocess.run(["docker", "stop", "presenton-e2e-fake"], capture_output=True)
r = user.post(S + "/edit", json={"image": data_url(src), "prompt": "x", "model": gemini}, timeout=200)
subprocess.run(["docker", "start", "presenton-e2e-fake"], capture_output=True)
check("arckep unreachable -> 503 with a readable message", r.status_code == 503 and "недоступен" in r.json().get("detail", ""), f"{r.status_code} {r.text[:200]}")
time.sleep(2)

if SLOW:
    fake(arckep="hang_create")
    t0 = time.time()
    r = user.post(S + "/generate", json={"prompt": "cat", "model": gemini}, timeout=300)
    check("arckep hangs -> readable unavailable error, not 500", r.status_code in (502, 503, 504), f"{r.status_code} {r.text[:200]} ({time.time()-t0:.0f}s)")
    fake(arckep="ok")

sys.exit(summary())
