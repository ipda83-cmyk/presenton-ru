"""Fake upstreams for the Presenton e2e stand: an OpenAI-compatible LLM and the arckep image API.

Costs nothing; faults are switched on via POST /control {"llm": mode, "arckep": mode, ...}.
LLM modes:  ok | http500 | fail_next:N (N x 504, then ok) | empty | garbage | hang
arckep modes: ok | create500 | create429 | balance | scope | job_failed | garbage | bad_image | download404 | upload500 | hang_create
YooKassa modes ("yookassa"): ok | create500 | saved_fail (saved-card charges are canceled)
arckep catalog and prices: GET /api/v1/models (the Studio's bundled snapshot), POST /api/v1/images/estimate
  ("estimate": ok | fail | odd — the cost in another field, nested).
RelaxNet Storage API ("storage"): ok | cdn_down (CDN 503, the fallback link works) | upload500 | down (everything 503)
A payment page (GET /yookassa/pay/<id>) has "Pay" / "Cancel"; paying sends the webhook
to Presenton like the real YooKassa (only the payment id matters: Presenton looks it up).
"""

import asyncio
import io
import itertools
import json
import random
import time
import uuid

from aiohttp import web
from PIL import Image, ImageDraw, ImageOps

STATE = {"llm": "ok", "arckep": "ok", "yookassa": "ok", "storage": "ok", "estimate": "ok", "llm_delay": 0.0, "fail_left": 0, "active_jobs": 0, "max_active_jobs": 0}
PAYMENTS: dict[str, dict] = {}
WEBHOOK_URL = "http://presenton-e2e/api/v1/billing/yookassa/webhook"
LOG: list[dict] = []
UPLOADS: dict[str, bytes] = {}
JOBS: dict[str, dict] = {}
FILES: dict[str, bytes] = {}
STORAGE: dict[str, bytes] = {}  # "users/7/presenton/<folder>/<ms>-<name>" -> bytes
STORAGE_PUBLIC = "http://presenton-e2e-fake:9000"
WORDS = (
    "solar panels cut energy costs for small offices while batteries store the midday surplus "
    "teams measure savings every quarter and share results with customers partners and investors"
).split()


# ---------------------------------------------------------------- JSON schema faker
def _text(min_len: int, max_len: int | None, seed: int) -> str:
    words = itertools.cycle(WORDS[seed % len(WORDS):] + WORDS[: seed % len(WORDS)])
    target = max(min_len, min(max_len or 60, 60))
    out = ""
    while len(out) < target:
        out = (out + " " + next(words)).strip()
    if max_len is not None:
        out = out[:max_len].rstrip() or "x" * min(max_len, max(min_len, 1))
    while len(out) < min_len:
        out += "x"
    return out


def fake(schema, root, seed=0, depth=0):
    if depth > 30:
        return None
    if not isinstance(schema, dict):
        return None
    if "$ref" in schema:
        ref = schema["$ref"].split("/")
        node = root
        for part in ref[1:]:
            node = node.get(part, {})
        return fake(node, root, seed, depth + 1)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        values = [value for value in schema["enum"] if value is not None] or schema["enum"]
        return values[seed % len(values)]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [option for option in schema[key] if option.get("type") != "null"] or schema[key]
            return fake(options[0], root, seed, depth + 1)
    if "allOf" in schema:
        merged = {}
        for part in schema["allOf"]:
            merged.update(part)
        return fake(merged, root, seed, depth + 1)
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((item for item in kind if item != "null"), "null")
    if kind == "object" or (kind is None and "properties" in schema):
        return {
            name: fake(prop, root, seed + index + 1, depth + 1)
            for index, (name, prop) in enumerate((schema.get("properties") or {}).items())
        }
    if kind == "array":
        low = schema.get("minItems", 1)
        high = schema.get("maxItems", max(low, 3))
        count = max(low, min(high, 3))
        return [fake(schema.get("items", {"type": "string"}), root, seed + i * 7, depth + 1) for i in range(count)]
    if kind == "string":
        if schema.get("format") in ("uri", "url"):
            return "https://example.com/picture.png"
        return _text(schema.get("minLength", 0), schema.get("maxLength"), seed)
    if kind == "integer":
        low = schema.get("minimum", 0)
        high = schema.get("maximum", low + 3)
        return int(low + (seed % (int(high) - int(low) + 1)) if high >= low else low)
    if kind == "number":
        return float(schema.get("minimum", 1))
    if kind == "boolean":
        return bool(seed % 2)
    if kind == "null":
        return None
    return _text(1, 40, seed)


# ---------------------------------------------------------------- LLM
def _answer(body: dict) -> str:
    response_format = body.get("response_format") or {}
    if response_format.get("type") == "json_schema":
        schema = response_format["json_schema"].get("schema") or {}
        return json.dumps(fake(schema, schema, seed=random.randint(0, 50)), ensure_ascii=False)
    if response_format.get("type") == "json_object":
        return "{}"
    return "Fake answer about solar panels"


def _completion(content: str, model: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


async def chat(request: web.Request):
    body = await request.json()
    rf = body.get("response_format") or {}
    has_image = any(
        isinstance(m.get("content"), list) and any(p.get("type") == "image_url" for p in m["content"])
        for m in body.get("messages", [])
    )
    LOG.append({"t": time.time(), "kind": "llm", "schema": (rf.get("json_schema") or {}).get("name"),
                "stream": bool(body.get("stream")), "images": has_image, "mode": STATE["llm"],
                "model": body.get("model"), "web_search": body.get("web_search")})
    mode = STATE["llm"]
    if mode == "http500":
        return web.json_response({"error": {"message": "fake upstream down"}}, status=500)
    if mode.startswith("fail_next") and STATE["fail_left"] > 0:
        STATE["fail_left"] -= 1
        return web.json_response({"error": {"message": "fake gateway timeout"}}, status=504)
    if mode == "hang":
        await asyncio.sleep(600)
    if STATE["llm_delay"]:
        await asyncio.sleep(STATE["llm_delay"])
    model = body.get("model", "fake-model")
    content = {"empty": "", "garbage": "this is { not json"}.get(mode) if mode in ("empty", "garbage") else _answer(body)
    if not body.get("stream"):
        return web.json_response(_completion(content, model))

    response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
    await response.prepare(request)
    base = {"id": f"chatcmpl-{uuid.uuid4().hex[:12]}", "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
    first = {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]}
    await response.write(f"data: {json.dumps(first)}\n\n".encode())
    for start in range(0, len(content), 60):
        chunk = {**base, "choices": [{"index": 0, "delta": {"content": content[start:start + 60]}, "finish_reason": None}]}
        await response.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
        await asyncio.sleep(0.01)
    done = {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
    usage = {**base, "choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}}
    await response.write(f"data: {json.dumps(done)}\n\n".encode())
    await response.write(f"data: {json.dumps(usage)}\n\n".encode())
    await response.write(b"data: [DONE]\n\n")
    await response.write_eof()
    return response


async def models(_request):
    return web.json_response({"object": "list", "data": [{"id": "fake-model", "object": "model", "owned_by": "e2e"}]})


# ---------------------------------------------------------------- arckep
def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _result_image(job: dict) -> bytes:
    refs = [UPLOADS[ref.rsplit("/", 1)[-1]] for ref in job["body"].get("reference_image_urls", []) if ref.rsplit("/", 1)[-1] in UPLOADS]
    if refs:
        base = Image.open(io.BytesIO(refs[0])).convert("RGB")
        # A visible "edit" plus a slight global tone drift, as real models do.
        result = ImageOps.mirror(base) if "view" in job["body"].get("prompt", "") else base.copy()
        draw = ImageDraw.Draw(result)
        w, h = result.size
        draw.ellipse((w * 0.35, h * 0.35, w * 0.65, h * 0.65), fill=(230, 80, 40))
        return _png(result.point(lambda v: min(255, v + 6)))
    color = tuple(random.randint(40, 220) for _ in range(3))
    image = Image.new("RGB", (768, 768), color)
    ImageDraw.Draw(image).text((20, 20), job["body"].get("prompt", "")[:60], fill=(255, 255, 255))
    return _png(image)


def _auth_ok(request) -> bool:
    return request.headers.get("Authorization", "").startswith("Bearer ")


async def uploads(request: web.Request):
    if not _auth_ok(request):
        return web.json_response({"error": {"message": "missing key"}}, status=401)
    if STATE["arckep"] == "upload500":
        return web.json_response({"error": {"message": "storage down"}}, status=500)
    reader = await request.multipart()
    part = await reader.next()
    data = await part.read()
    name = f"{uuid.uuid4().hex}.png"
    UPLOADS[name] = bytes(data)
    LOG.append({"t": time.time(), "kind": "upload", "bytes": len(data)})
    return web.json_response({"url": f"http://{request.host}/files/uploads/{name}"})


async def create_job(request: web.Request):
    if not _auth_ok(request):
        return web.json_response({"error": {"message": "missing key"}}, status=401)
    body = await request.json()
    mode = STATE["arckep"]
    LOG.append({"t": time.time(), "kind": "job", "model": body.get("model"), "prompt": body.get("prompt", "")[:600],
                "refs": len(body.get("reference_image_urls", [])), "mode": mode, "keys": sorted(body)})
    if mode == "create500":
        return web.json_response({"error": {"message": "internal error"}}, status=500)
    if mode == "create429":
        return web.json_response({"error": {"message": "too many active jobs", "code": "RATE_LIMITED"}}, status=429)
    if mode == "balance":
        return web.json_response({"error": {"message": "Insufficient balance", "code": "INSUFFICIENT_BALANCE"}}, status=402)
    if mode == "scope":
        return web.json_response({"error": {"message": "API key is missing required scope 'images:write'"}}, status=403)
    if mode == "garbage":
        return web.Response(text="<html>bad gateway</html>", status=200)
    if mode == "hang_create":
        await asyncio.sleep(600)
    if STATE["active_jobs"] >= 5:
        return web.json_response({"error": {"message": "too many active jobs", "code": "RATE_LIMITED"}}, status=429)
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"body": body, "ready_at": time.time() + 2.5, "mode": mode}
    STATE["active_jobs"] += 1
    STATE["max_active_jobs"] = max(STATE["max_active_jobs"], STATE["active_jobs"])
    return web.json_response({"id": job_id, "status": "queued"})


async def job_status(request: web.Request):
    job = JOBS.get(request.match_info["job_id"])
    if job is None:
        return web.json_response({"error": {"message": "not found"}}, status=404)
    if time.time() < job["ready_at"]:
        return web.json_response({"id": request.match_info["job_id"], "status": "processing"})
    if not job.get("finished"):
        job["finished"] = True
        STATE["active_jobs"] -= 1
    if job["mode"] == "job_failed":
        return web.json_response({"status": "failed", "error": {"message": "content policy violation", "code": "MODERATION"}})
    count = max(1, int(job["body"].get("n") or job["body"].get("count") or 1))
    urls = []
    for _ in range(count):
        name = f"{uuid.uuid4().hex}.png"
        FILES[name] = b"definitely not a png" if job["mode"] == "bad_image" else _result_image(job)
        urls.append(f"http://{request.host}/files/out/{name}" + ("-missing" if job["mode"] == "download404" else ""))
    return web.json_response({"status": "completed", "output": {"images": [{"url": url} for url in urls]}})


async def files(request: web.Request):
    name = request.match_info["name"]
    data = FILES.get(name) or UPLOADS.get(name)
    if data is None:
        return web.Response(status=404)
    return web.Response(body=data, content_type="image/png")


# ---------------------------------------------------------------- YooKassa
def _kassa_auth(request) -> bool:
    return request.headers.get("Authorization", "").startswith("Basic ")


async def kassa_create(request: web.Request):
    if not _kassa_auth(request):
        return web.json_response({"type": "error", "code": "invalid_credentials", "description": "auth"}, status=401)
    body = await request.json()
    LOG.append({"t": time.time(), "kind": "yookassa", "body": body, "idempotence": request.headers.get("Idempotence-Key")})
    if STATE["yookassa"] == "create500":
        return web.json_response({"type": "error", "code": "internal_server_error"}, status=500)
    receipt = body.get("receipt") or {}
    if not (receipt.get("customer") or {}).get("email") or not receipt.get("items"):
        return web.json_response({"type": "error", "code": "invalid_request", "description": "Receipt is missing or illegal"}, status=400)
    payment_id = f"2f{uuid.uuid4().hex[:6]}-000f-5000-9000-{uuid.uuid4().hex[:12]}"
    payment = {
        "id": payment_id,
        "status": "pending",
        "paid": False,
        "amount": body["amount"],
        "description": body.get("description"),
        "metadata": body.get("metadata") or {},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "_save": bool(body.get("save_payment_method")),
        "_return": (body.get("confirmation") or {}).get("return_url"),
    }
    if body.get("payment_method_id"):
        ok = STATE["yookassa"] != "saved_fail"
        payment.update(status="succeeded" if ok else "canceled", paid=ok,
                       payment_method={"id": body["payment_method_id"], "saved": True, "type": "bank_card"})
    else:
        payment["confirmation"] = {"type": "redirect", "confirmation_url": f"http://presenton-e2e-fake:9000/yookassa/pay/{payment_id}"}
    PAYMENTS[payment_id] = payment
    return web.json_response({k: v for k, v in payment.items() if not k.startswith("_")})


async def kassa_get(request: web.Request):
    if not _kassa_auth(request):
        return web.json_response({"type": "error", "code": "invalid_credentials"}, status=401)
    payment = PAYMENTS.get(request.match_info["payment_id"])
    if payment is None:
        return web.json_response({"type": "error", "code": "not_found"}, status=404)
    return web.json_response({k: v for k, v in payment.items() if not k.startswith("_")})


async def kassa_page(request: web.Request):
    payment = PAYMENTS.get(request.match_info["payment_id"])
    if payment is None:
        return web.Response(status=404, text="no such payment")
    amount = payment["amount"]["value"]
    html = f"""<!doctype html><meta charset="utf-8"><title>Fake YooKassa</title>
<h1>Оплата {amount} ₽</h1><p>{payment.get("description") or ""}</p>
<form method="post" action="/yookassa/pay/{payment["id"]}/succeed"><button id="pay">Оплатить</button></form>
<form method="post" action="/yookassa/pay/{payment["id"]}/cancel"><button id="cancel">Отменить</button></form>"""
    return web.Response(text=html, content_type="text/html")


async def _notify(event: str, payment_id: str) -> None:
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            # Deliberately a lie about the amount: Presenton must look the payment up itself.
            await session.post(WEBHOOK_URL, json={"type": "notification", "event": event, "object": {"id": payment_id, "status": "succeeded", "amount": {"value": "99999.00", "currency": "RUB"}}})
    except Exception as error:  # the stand may be down
        LOG.append({"t": time.time(), "kind": "webhook_failed", "error": repr(error)})


async def kassa_decide(request: web.Request):
    payment = PAYMENTS.get(request.match_info["payment_id"])
    if payment is None:
        return web.Response(status=404)
    if request.match_info["decision"] == "succeed":
        payment.update(status="succeeded", paid=True)
        if payment["_save"]:
            payment["payment_method"] = {"id": f"pm-{uuid.uuid4().hex[:8]}", "saved": True, "type": "bank_card",
                                         "card": {"last4": "4477", "card_type": "MasterCard"}}
        await _notify("payment.succeeded", payment["id"])
    else:
        payment.update(status="canceled", paid=False)
        await _notify("payment.canceled", payment["id"])
    raise web.HTTPFound(payment["_return"] or "/")


async def kassa_set(request: web.Request):
    """Test helper: change a payment as YooKassa would (no webhook)."""
    body = await request.json()
    payment = PAYMENTS[request.match_info["payment_id"]]
    payment.update({k: v for k, v in body.items() if k in ("status", "paid", "amount", "metadata")})
    return web.json_response(payment)


# ---------------------------------------------------------------- arckep catalog and prices
CATALOG_PATH = "/app/servers/fastapi/services/studio/catalog_snapshot.json"
FAKE_COSTS = {"1K": 6.0, "2K": 9.0, "4K": 14.0, "low": 1.0, "medium": 5.0, "high": 20.0, "xhigh": 30.0, "max": 40.0}
# The measured costs of the first Studio models, so earlier checks keep their prices.
MODEL_COSTS = {
    "gemini-nano-banana-2.1": {"1K": 8.13, "2K": 12.26, "4K": 18.33},
    "gemini-3-pro-image": {"1K": 17.0, "2K": 17.0, "4K": 26.56},
}


async def models_catalog(request: web.Request):
    if not _auth_ok(request):
        return web.json_response({"error": {"message": "missing key"}}, status=401)
    try:
        with open(CATALOG_PATH, encoding="utf-8") as handle:
            images = json.load(handle)["models"]
    except OSError:  # an older image without the snapshot
        images = [{"id": "gemini-nano-banana-2.1", "provider": "gemini", "modes": ["generate", "edit_with_reference"],
                   "aspect_ratios": ["1:1", "16:9"], "resolutions": ["1K", "2K"], "max_images": 1, "max_reference_images": 14}]
    data = [{**model, "type": "image"} for model in images] + [{"id": "gpt-5-chat", "type": "chat"}]
    return web.json_response({"object": "list", "data": data})


async def estimate(request: web.Request):
    if not _auth_ok(request):
        return web.json_response({"error": {"message": "missing key"}}, status=401)
    body = await request.json()
    LOG.append({"t": time.time(), "kind": "estimate", "body": body})
    if STATE["estimate"] == "fail":
        return web.json_response({"error": {"message": "estimate unavailable"}}, status=503)
    known = MODEL_COSTS.get(body.get("model") or "")
    if known:
        cost = known.get(body.get("resolution") or "1K", known["1K"])
    else:
        cost = FAKE_COSTS.get(body.get("resolution") or "", 6.0) + FAKE_COSTS.get(body.get("quality") or "", 0.0)
    if STATE["estimate"] == "odd":
        return web.json_response({"model": body.get("model"), "estimate": {"total": str(cost), "currency": "RUB"}})
    return web.json_response({"model": body.get("model"), "cost_rub": cost, "currency": "RUB"})


# ---------------------------------------------------------------- RelaxNet Storage API
def _storage_down(request: web.Request) -> web.Response | None:
    if STATE["storage"] == "down":
        return web.Response(status=503, text="storage is down")
    if not request.headers.get("Authorization", "").startswith("Bearer "):
        return web.json_response({"success": False, "error": "unauthorized"}, status=401)
    return None


def _storage_links(key: str) -> dict:
    return {"url": f"{STORAGE_PUBLIC}/cdn/{key}", "fallbackUrl": f"{STORAGE_PUBLIC}/files-fallback/{key}"}


async def storage_upload(request: web.Request):
    if (error := _storage_down(request)) is not None:
        return error
    if STATE["storage"] == "upload500":
        return web.Response(status=500, text="upload failed")
    form = await request.post()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "file"):
        return web.json_response({"success": False, "error": "file is required"}, status=400)
    folder = "/".join(part for part in str(form.get("path") or "").split("/") if part not in ("", ".", ".."))
    name = upload.filename.replace("/", "_")
    webp = str(form.get("webp", "true")).lower() != "false"
    if webp and name.lower().endswith((".png", ".jpg", ".jpeg")):
        name = name.rsplit(".", 1)[0] + ".webp"  # like the real API: raster images become WebP
    key = "/".join(part for part in ("users/7/presenton", folder, f"{int(time.time() * 1000)}-{name}") if part)
    STORAGE[key] = upload.file.read()
    LOG.append({"t": time.time(), "kind": "storage_upload", "key": key, "size": len(STORAGE[key])})
    return web.json_response({"success": True, "path": key, "webp": webp, **_storage_links(key)})


async def storage_files(request: web.Request):
    if (error := _storage_down(request)) is not None:
        return error
    path = request.query.get("path", "")
    if request.method == "DELETE":
        key = path.split("/cdn/", 1)[-1] if "/cdn/" in path else path
        if key not in STORAGE:
            return web.json_response({"success": False, "error": "not found"}, status=404)
        del STORAGE[key]
        LOG.append({"t": time.time(), "kind": "storage_delete", "key": key})
        return web.json_response({"success": True, "deleted": key})
    prefix = "users/7/presenton/" + path.strip("/")
    files = [
        {"path": key, "size": len(data), **_storage_links(key)}
        for key, data in STORAGE.items()
        if key.startswith(prefix)
    ]
    return web.json_response({"success": True, "files": files})


async def storage_object(request: web.Request):
    if STATE["storage"] == "down" or (STATE["storage"] == "cdn_down" and request.path.startswith("/cdn/")):
        return web.Response(status=503)
    data = STORAGE.get(request.match_info["key"])
    if data is None:
        return web.Response(status=404)
    return web.Response(body=data, content_type="application/octet-stream")


async def storage_dump(_: web.Request):
    """Test helper: what the storage holds."""
    return web.json_response({key: len(data) for key, data in STORAGE.items()})


# ---------------------------------------------------------------- control
async def control(request: web.Request):
    if request.method == "POST":
        body = await request.json()
        for key in ("llm", "arckep", "yookassa", "storage", "estimate", "llm_delay"):
            if key in body:
                STATE[key] = body[key]
        if str(STATE["llm"]).startswith("fail_next:"):
            STATE["fail_left"] = int(STATE["llm"].split(":")[1])
        if body.get("reset_log"):
            LOG.clear()
            STATE["max_active_jobs"] = 0
    return web.json_response({"state": STATE, "log": LOG[-400:]})


app = web.Application(client_max_size=64 * 1024 * 1024)
app.add_routes([
    web.post("/v1/chat/completions", chat),
    web.get("/v1/models", models),
    web.post("/api/v1/uploads", uploads),
    web.post("/api/v1/images/generations", create_job),
    web.get("/api/v1/models", models_catalog),
    web.post("/api/v1/images/estimate", estimate),
    web.get("/api/v1/images/generations/{job_id}", job_status),
    web.get("/files/uploads/{name}", files),
    web.get("/files/out/{name}", files),
    web.post("/yookassa/v3/payments", kassa_create),
    web.get("/yookassa/v3/payments/{payment_id}", kassa_get),
    web.get("/yookassa/pay/{payment_id}", kassa_page),
    web.post("/yookassa/pay/{payment_id}/{decision:succeed|cancel}", kassa_decide),
    web.post("/yookassa/test/{payment_id}", kassa_set),
    web.post("/storage/upload", storage_upload),
    web.get("/storage/files", storage_files),
    web.delete("/storage/files", storage_files),
    web.get("/storage/test/dump", storage_dump),
    web.get("/cdn/{key:.+}", storage_object),
    web.get("/files-fallback/{key:.+}", storage_object),
    web.get("/control", control),
    web.post("/control", control),
])

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=9000)
