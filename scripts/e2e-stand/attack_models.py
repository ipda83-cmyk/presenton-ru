"""Studio image models from arckep's catalog (Admin → Models), on a separate stand.

The administrator refreshes the catalog, asks prices, turns models on and off,
renames them and sets modes, a manual cost and the model for slide pictures;
users see only the chosen models and pay cost x markup; a model without a
price is refused instead of being free.

    python scripts/e2e-stand/attack_models.py

Presenton: http://127.0.0.1:5059 (container presenton-models), fake arckep on :9056.
Needs the presenton-ru-production image built from this tree.
"""

import os
import subprocess
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
os.environ.setdefault("E2E_BASE", "http://127.0.0.1:5059")
sys.path.insert(0, HERE)

from common import BASE, FAKE, check, fake, fake_log, summary  # noqa: E402

IMAGE = os.environ.get("PRESENTON_IMAGE", "presenton-ru-production:latest")
NETWORK = "presenton-e2e"
APP = "presenton-models"
FAKE_CONTAINER = "presenton-e2e-fake"
ADMIN = {"username": "models-admin", "password": "models-admin-pass-1"}
USER = {"username": "models-user", "password": "models-user-pass-1"}
S = f"{BASE}/api/v1/studio"
A = f"{BASE}/api/v1/admin/studio"


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
        "run", "-d", "--name", APP, "--network", NETWORK, "-p", "127.0.0.1:5059:80",
        "-v", f"{os.path.join(ROOT, 'servers', 'fastapi')}:/app/servers/fastapi",
        "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "MEM0_ENABLED=false", "-e", "WEB_GROUNDING=false",
        "-e", "LLM=custom", "-e", f"CUSTOM_LLM_URL=http://{FAKE_CONTAINER}:9000/v1",
        "-e", "CUSTOM_MODEL=fake-model", "-e", "CUSTOM_LLM_API_KEY=e2e-test",
        "-e", "STUDIO_API_KEY=e2e-test", "-e", f"STUDIO_BASE_URL=http://{FAKE_CONTAINER}:9000/api/v1",
        "-e", "IMAGE_PROVIDER=pexels", "-e", "PEXELS_API_KEY=unused",
        "-e", "PRESENTON_COMMUNITY_ENABLED=false",
        IMAGE,
    )
    for _ in range(100):
        try:
            if requests.get(f"{BASE}/api/v1/auth/status", timeout=3).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1.5)
    sys.exit("Presenton did not start")


def login(creds: dict) -> requests.Session:
    session = requests.Session()
    session.cookies.set("NEXT_LOCALE", "ru")
    response = session.post(f"{BASE}/api/v1/auth/login", json=creds, timeout=30)
    if response.status_code != 200:
        sys.exit(f"login {creds['username']}: {response.status_code} {response.text[:200]}")
    return session


def balance(session: requests.Session) -> int:
    return session.get(f"{BASE}/api/v1/billing/me", timeout=60).json()["balance"]


def last_job() -> dict:
    jobs = [entry for entry in fake_log() if entry.get("kind") == "job"]
    return jobs[-1] if jobs else {}


def main() -> int:
    start()
    fake(arckep="ok", estimate="ok", reset_log=True)
    requests.post(f"{BASE}/api/v1/auth/setup", json=ADMIN, timeout=30)
    admin = login(ADMIN)
    admin.post(f"{BASE}/api/v1/admin/users", json=USER, timeout=30)
    user = login(USER)
    check("a user starts with the bonus", balance(user) == 100)

    state = admin.get(f"{A}/models", timeout=60).json()
    check("the starting set is on", [m["key"] for m in state["models"] if m["enabled"]] == [
        "gemini-nano-banana-2.1", "gemini-3-pro-image", "gpt-image-2.5-sunburst", "flux-2-pro", "seedream-5.0-pro", "recraft-v4.1-vector",
    ], str([m["key"] for m in state["models"] if m["enabled"]]))
    state = admin.post(f"{A}/catalog/refresh", timeout=60).json()
    check("the catalog comes from arckep", state["catalog"]["source"] == "arckep" and state["catalog"]["count"] == 37, str(state["catalog"]))
    check("users cannot open the admin API", user.get(f"{A}/models", timeout=30).status_code in (401, 403, 404))

    flux = admin.post(f"{A}/models/flux-2-pro/estimate", timeout=60).json()
    check("arckep's estimate prices FLUX", flux["costs"]["2K|"]["cost"] == 9.0 and flux["costs"]["2K|"]["price"] == 14, str(flux["costs"]))
    fake(estimate="odd")
    gpt = admin.post(f"{A}/models/gpt-image-2.5-sunburst/estimate", timeout=60).json()
    check("an estimate in another shape is still read", gpt["costs"]["1K|medium"]["cost"] == 11.0, str(gpt["costs"].get("1K|medium")))
    fake(estimate="ok")

    body = {
        "default_model": "flux-2-pro",
        "markup": 1.45,
        "slide_image_model": "flux-2-pro",
        "models": {
            **{m["key"]: {"enabled": m["enabled"], "title": m["title"], "order": m["order"], "modes": m["modes"]} for m in state["models"] if m["enabled"]},
            "recraft-v4.1-vector": {"enabled": False, "title": "Recraft", "order": 9, "modes": ["generate"]},
            "midjourney": {"enabled": True, "title": "Midjourney", "order": 7, "modes": ["generate"], "markup": 2, "costs": {"1K|fast": 10}},
            "flux-2-pro": {"enabled": True, "title": "FLUX Про", "order": 0, "modes": ["generate", "edit"]},
        },
    }
    saved = admin.put(f"{A}/models", json=body, timeout=60)
    check("the administrator saves the models", saved.status_code == 200, saved.text[:200])

    config = user.get(f"{S}/config", timeout=60).json()
    titles = [m["title"] for m in config["models"]]
    check("users see the chosen models in order", titles[0] == "FLUX Про" and "Midjourney" in titles and "Recraft" not in titles, str(titles))
    check("the default model", config["default_model"] == "flux-2-pro")
    check("prices for users", config["prices"]["flux-2-pro"]["units"]["2K|"] == 13.05, str(config["prices"].get("flux-2-pro")))

    before = balance(user)
    r = user.post(f"{S}/generate", json={"prompt": "город", "model": "flux-2-pro", "resolution": "2K", "aspect_ratio": "16:9"}, timeout=120)
    check("FLUX generates", r.status_code == 200, r.text[:200])
    job = last_job()
    check("arckep gets FLUX's own options", job.get("model") == "flux-2-pro" and "aspect_ratio" in job.get("keys", []), str(job))
    check("FLUX costs cost x markup", balance(user) == before - 14, f"{before} -> {balance(user)}")

    before = balance(user)
    r = user.post(f"{S}/generate", json={"prompt": "кот", "model": "midjourney", "quality": "fast"}, timeout=120)
    check("Midjourney generates", r.status_code == 200, r.text[:200])
    check("a manual cost and an own markup", balance(user) == before - 20, f"{before} -> {balance(user)}")

    r = user.post(f"{S}/generate", json={"prompt": "кот", "model": "recraft-v4.1-vector"}, timeout=60)
    check("a model turned off is refused", r.status_code == 400, r.text[:200])
    r = user.post(f"{S}/storyboard", json={"image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=", "view": "front", "model": "flux-2-pro"}, timeout=60)
    check("a mode turned off is refused, in Russian", r.status_code == 400 and "режиме" in r.json().get("detail", ""), r.text[:200])

    # A model arckep cannot price yet (estimates fail): refused for payers, not free.
    fake(estimate="fail")
    body["models"]["wan2.7-image"] = {"enabled": True, "title": "Wan", "order": 8, "modes": ["generate"]}
    admin.put(f"{A}/models", json=body, timeout=60)
    before = balance(user)
    r = user.post(f"{S}/generate", json={"prompt": "море", "model": "wan2.7-image", "resolution": "1K"}, timeout=60)
    check("no price: refused, not free", r.status_code == 503 and balance(user) == before, f"{r.status_code} {r.text[:200]}")
    r = admin.post(f"{S}/generate", json={"prompt": "море", "model": "wan2.7-image", "resolution": "1K"}, timeout=120)
    check("administrators still generate without a price", r.status_code == 200, r.text[:200])
    # A model priced earlier keeps its price while arckep cannot estimate.
    before = balance(user)
    r = user.post(f"{S}/generate", json={"prompt": "море", "model": "flux-2-pro", "resolution": "2K"}, timeout=120)
    check("an earlier estimate still prices FLUX", r.status_code == 200 and balance(user) == before - 14, f"{r.status_code} {before} -> {balance(user)}")
    fake(estimate="ok")

    # Slide pictures by the chosen Studio model (the image provider says Pexels).
    jobs_before = len([e for e in fake_log() if e.get("kind") == "job"])
    r = admin.post(
        f"{BASE}/api/v1/ppt/presentation/generate",
        json={"content": "Города будущего", "n_slides": 3, "language": "Russian", "export_as": "pptx"},
        timeout=600,
    )
    slide_jobs = [e for e in fake_log() if e.get("kind") == "job"][jobs_before:]
    check("a presentation is made", r.status_code == 200, r.text[:300])
    check("its pictures come from the chosen Studio model", slide_jobs and all(job.get("model") == "flux-2-pro" for job in slide_jobs),
          str([job.get("model") for job in slide_jobs]))
    check("slide pictures ask for people of Slavic appearance",
          slide_jobs and all("Slavic (Eastern European, Russian) appearance" in job.get("prompt", "") for job in slide_jobs),
          str([job.get("prompt", "")[-160:] for job in slide_jobs[:1]]))
    studio_jobs = [e for e in fake_log() if e.get("kind") == "job" and e.get("prompt", "").startswith("город")]
    check("Studio prompts stay as the user wrote them", studio_jobs and "Slavic" not in studio_jobs[0]["prompt"], str(studio_jobs[:1]))

    # Own templates: a regular user checks the fonts of a PPTX; deleting fonts stays for administrators.
    subprocess.run(["docker", "exec", APP, "/opt/venv/bin/python", "-c",
                    "from pptx import Presentation; p = Presentation(); "
                    "s = p.slides.add_slide(p.slide_layouts[0]); s.shapes.title.text = 'Шаблон'; p.save('/tmp/own.pptx')"],
                   check=True, capture_output=True)
    pptx_path = os.path.join(HERE, ".relax-logs", "own.pptx")
    os.makedirs(os.path.dirname(pptx_path), exist_ok=True)
    subprocess.run(["docker", "cp", f"{APP}:/tmp/own.pptx", pptx_path], check=True, capture_output=True)
    with open(pptx_path, "rb") as handle:
        r = user.post(f"{BASE}/api/v1/ppt/fonts/check", files={"pptx_file": ("own.pptx", handle.read())}, timeout=120)
    check("a user checks the fonts of their PPTX", r.status_code == 200 and "available_fonts" in r.text, f"{r.status_code} {r.text[:200]}")
    r = user.delete(f"{BASE}/api/v1/ppt/fonts/delete/anything.ttf", timeout=30)
    check("deleting fonts is still for administrators", r.status_code == 403, f"{r.status_code} {r.text[:120]}")

    # Community is off on this deployment: an immediate answer, no 30 s wait.
    started = time.time()
    r = user.get(f"{BASE}/api/v1/ppt/community/presentations?page=1&page_size=20", timeout=60)
    check("community is off and answers at once", r.status_code == 404 and time.time() - started < 5, f"{r.status_code} {time.time() - started:.1f}s")

    estimates = [e for e in fake_log() if e.get("kind") == "estimate"]
    check("estimates are cached, not asked for every request", len(estimates) < 40, str(len(estimates)))
    logs = subprocess.run(["docker", "logs", APP], capture_output=True, text=True, encoding="utf-8", errors="replace")
    errors = [line for line in (logs.stdout + logs.stderr).splitlines() if "Traceback" in line]
    check("no tracebacks", not errors, "\n".join(errors[:3]))
    return summary()


if __name__ == "__main__":
    sys.exit(main())
