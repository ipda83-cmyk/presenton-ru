"""Attack billing on the e2e stand: charges, refunds, races, YooKassa top-ups, webhooks, auto top-up."""

import concurrent.futures
import secrets
import sys
import time

import requests

from common import BASE, FAKE, check, data_url, fake, fake_log, login, png, summary

B = f"{BASE}/api/v1/billing"
S = f"{BASE}/api/v1/studio"
P = f"{BASE}/api/v1/ppt/presentation"
fake(llm="ok", arckep="ok", yookassa="ok", llm_delay=0, reset_log=True)

admin = login("admin")
anon = requests.Session()
# A fresh payer each run: the signup bonus and the once-an-hour auto top-up start clean.
payer_name = f"e2e-payer-{int(time.time())}"
payer_password = secrets.token_urlsafe(12)
created = admin.post(f"{BASE}/api/v1/admin/users", json={"username": payer_name, "password": payer_password}, timeout=30)
assert created.status_code == 201, created.text
payer_id = created.json()["id"]
payer = requests.Session()
payer.cookies.set("NEXT_LOCALE", "ru")
assert payer.post(f"{BASE}/api/v1/auth/login", json={"username": payer_name, "password": payer_password}, timeout=30).status_code == 200


def balance() -> int:
    return payer.get(f"{B}/me", timeout=30).json()["balance"]


# ---------------------------------------------------------------- who pays
me = payer.get(f"{B}/me", timeout=30).json()
check("payer: billing on, not free, 100 RUB", me["enabled"] and not me["free"] and me["balance"] == 100, str(me)[:200])
check("payments available, offer link, 10 RUB per slide", me["payments_available"] and me["offer_url"] and me["prices"]["per_slide"] == 10, str(me)[:200])
check("admin: free", admin.get(f"{B}/me", timeout=30).json()["free"] is True)
check("anon /billing/me -> 401", anon.get(f"{B}/me", timeout=30).status_code == 401)
check("user cannot see admin billing -> 403", payer.get(f"{BASE}/api/v1/admin/billing/accounts", timeout=30).status_code == 403)
check("user cannot credit themselves -> 403", payer.post(f"{BASE}/api/v1/admin/billing/adjust", json={"user_id": payer_id, "amount": 9999}, timeout=30).status_code == 403)
cfg = payer.get(f"{S}/config", timeout=30).json()
check("studio config: charged + prices", cfg["charged"] is True and cfg["prices"]["nano_banana_pro"]["resolution"]["1K"] == 25, str(cfg.get("prices"))[:200])
check("studio config: admin not charged", admin.get(f"{S}/config", timeout=30).json()["charged"] is False)

# ---------------------------------------------------------------- Studio charges and refunds
r = payer.post(f"{S}/generate", json={"prompt": "робот", "model": "nano_banana_pro"}, timeout=120)
check("Nano Banana Pro 1K costs 25", r.status_code == 200 and balance() == 75, f"{r.status_code} {balance()}")
fake(arckep="create500")
r = payer.post(f"{S}/generate", json={"prompt": "робот", "model": "nano_banana_pro"}, timeout=120)
check("arckep failure -> 502 and the money is back", r.status_code == 502 and balance() == 75, f"{r.status_code} {balance()}")
fake(arckep="ok")
r = admin.post(f"{S}/generate", json={"prompt": "робот", "model": "nano_banana_pro"}, timeout=120)
check("admin generates for free", r.status_code == 200)

src = data_url(png())


def view(_):
    return payer.post(f"{S}/storyboard", json={"image": src, "view": "front", "model": "nano_banana_2"}, timeout=200).status_code


with concurrent.futures.ThreadPoolExecutor(10) as pool:
    codes = list(pool.map(view, range(10)))
check("10 parallel views at 75 RUB: exactly 6 paid (12 each), 4 refused", codes.count(200) == 6 and codes.count(402) == 4, str(codes))
check("balance never below zero: 3 left", balance() == 3, str(balance()))
r = payer.post(f"{S}/generate", json={"prompt": "кот", "model": "nano_banana_2"}, timeout=60)  # session locale: ru
check("402 says how much is needed and left (RU)", r.status_code == 402 and "нужно 12 ₽, на балансе 3 ₽" in r.json()["detail"], r.text[:200])

# ---------------------------------------------------------------- presentations: early refusal
r = payer.post(f"{P}/create", json={"content": "Солнечные панели", "n_slides": 5, "language": "Russian"}, timeout=60)
check("create 5 slides with 3 RUB -> 402 before any outline", r.status_code == 402 and "50 ₽" in r.json()["detail"], r.text[:200])

# ---------------------------------------------------------------- top-up through (fake) YooKassa
for body, code in [
    ({"amount": 333, "email": "p@example.com"}, 400),
    ({"amount": 500, "email": "nope"}, 400),
    ({"amount": 500, "email": "p@example.com", "save_card": True}, 400),
]:
    check(f"topup {body} -> {code}", payer.post(f"{B}/topup", json=body, timeout=30).status_code == code)
fake(reset_log=True)
r = payer.post(f"{B}/topup", json={"amount": 500, "email": "p@example.com", "save_card": True, "consent": True}, timeout=30)
ok = check("topup 500 with card saving -> payment page", r.status_code == 200 and "/yookassa/pay/" in r.json()["confirmation_url"], r.text[:200])
if ok:
    invoice = r.json()["invoice_id"]
    payment_id = r.json()["confirmation_url"].rsplit("/", 1)[-1]
    sent = [e for e in fake_log() if e["kind"] == "yookassa"][-1]
    receipt = sent["body"]["receipt"]
    check("54-FZ receipt: email, service item, VAT code 1", receipt["customer"]["email"] == "p@example.com" and receipt["items"][0]["vat_code"] == 1 and receipt["items"][0]["payment_subject"] == "service", str(receipt))
    check("idempotence key = invoice", sent["idempotence"] == invoice, str(sent["idempotence"]))
    check("return url leads back to /billing", sent["body"]["confirmation"]["return_url"].endswith(f"/billing?payment={invoice}"), sent["body"]["confirmation"]["return_url"])
    check("not paid yet: balance unchanged", balance() == 3)
    # The fake YooKassa's webhook lies about the amount (99999): only the lookup counts.
    paid = requests.post(f"{FAKE}/yookassa/pay/{payment_id}/succeed", allow_redirects=False, timeout=30)
    time.sleep(1)
    check("paid -> webhook credits exactly 500", balance() == 503, str(balance()))
    checked = payer.post(f"{B}/payments/{invoice}/check", timeout=30).json()
    check("return check says completed", checked["status"] == "completed" and checked["balance"] == 503, str(checked))
    for _ in range(3):
        requests.post(f"{BASE}/api/v1/billing/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": payment_id}}, timeout=30)
    check("replayed webhooks credit nothing more", balance() == 503, str(balance()))
    me = payer.get(f"{B}/me", timeout=30).json()
    check("card saved after the paid top-up", me["card"] and me["card"]["last4"] == "4477", str(me["card"]))
    check("other users cannot check someone's payment -> 404", admin.post(f"{B}/payments/{invoice}/check", timeout=30).status_code == 404)

r = requests.post(f"{BASE}/api/v1/billing/yookassa/webhook", json={"event": "payment.succeeded", "object": {"id": "forged-123", "amount": {"value": "100000.00"}}}, timeout=30)
check("forged webhook (unknown id) -> 200, nothing credited", r.status_code == 200 and balance() == 503, f"{r.status_code} {balance()}")
check("webhook with broken JSON -> 400", requests.post(f"{BASE}/api/v1/billing/yookassa/webhook", data="{x", headers={"Content-Type": "application/json"}, timeout=30).status_code == 400)
check("webhook GET -> 405", requests.get(f"{BASE}/api/v1/billing/yookassa/webhook", timeout=30).status_code == 405)

r = payer.post(f"{B}/topup", json={"amount": 100, "email": "p@example.com"}, timeout=30).json()
tampered = r["confirmation_url"].rsplit("/", 1)[-1]
requests.post(f"{FAKE}/yookassa/test/{tampered}", json={"status": "succeeded", "paid": True, "amount": {"value": "1.00", "currency": "RUB"}}, timeout=30)
status = payer.post(f"{B}/payments/{r['invoice_id']}/check", timeout=30).json()["status"]
check("paid less than invoiced -> not credited", status == "pending" and balance() == 503, f"{status} {balance()}")

r = payer.post(f"{B}/topup", json={"amount": 100, "email": "p@example.com"}, timeout=30).json()
requests.post(f"{FAKE}/yookassa/pay/{r['confirmation_url'].rsplit('/', 1)[-1]}/cancel", allow_redirects=False, timeout=30)
time.sleep(1)
check("canceled payment -> failed, nothing credited", payer.post(f"{B}/payments/{r['invoice_id']}/check", timeout=30).json()["status"] == "failed" and balance() == 503)

fake(yookassa="create500")
r = payer.post(f"{B}/topup", json={"amount": 100, "email": "p@example.com"}, timeout=30)
check("YooKassa down -> 503 with a readable message", r.status_code == 503 and "недоступен" in r.json()["detail"], f"{r.status_code} {r.text[:160]}")
fake(yookassa="ok")

# ---------------------------------------------------------------- presentation generation through the API
r = payer.post(f"{P}/generate", json={"content": "Солнечные панели для офиса", "n_slides": 3, "language": "Russian", "export_as": "pptx"}, timeout=600)
check("API generate 3 slides -> 200, 30 RUB", r.status_code == 200 and balance() == 473, f"{r.status_code} {r.text[:200]} balance={balance()}")
fake(llm="http500")
r = payer.post(f"{P}/generate", json={"content": "Ещё одна", "n_slides": 3, "language": "Russian", "export_as": "pptx"}, timeout=600)
check("API generate fails -> error and nothing kept", r.status_code >= 400 and balance() == 473, f"{r.status_code} balance={balance()}")
fake(llm="ok")
history = payer.get(f"{B}/history", timeout=30).json()["entries"]
check("history: presentation charge settled", any(e["reason"] == "presentation" and e["kind"] == "charge" and not e["pending"] for e in history), str(history[:3])[:300])

# ---------------------------------------------------------------- auto top-up
r = payer.put(f"{B}/auto-topup", json={"enabled": True, "threshold": 500, "amount": 1000}, timeout=30)
check("auto top-up on (card saved)", r.status_code == 200 and r.json()["auto_topup"]["enabled"], r.text[:200])
fake(reset_log=True)
payer.post(f"{S}/generate", json={"prompt": "кот", "model": "nano_banana_2"}, timeout=120)  # 473 - 12 = 461 < 500
for _ in range(20):
    if balance() > 1000:
        break
    time.sleep(0.5)
check("balance below the threshold -> card charged 1000 in the background", balance() == 1461, str(balance()))
saved_calls = [e for e in fake_log() if e["kind"] == "yookassa" and e["body"].get("payment_method_id")]
check("auto top-up used the saved card with a receipt", len(saved_calls) == 1 and saved_calls[0]["body"]["receipt"]["customer"]["email"] == "p@example.com", str(saved_calls)[:300])
admin.post(f"{BASE}/api/v1/admin/billing/adjust", json={"user_id": payer_id, "amount": 20, "mode": "set"}, timeout=30)
payer.post(f"{S}/generate", json={"prompt": "кот", "model": "nano_banana_2"}, timeout=120)
time.sleep(2)
check("second dip within the hour -> no second charge", balance() == 8 and len([e for e in fake_log() if e["kind"] == "yookassa"]) == 1, str(balance()))
check("forget card -> auto top-up off", payer.delete(f"{B}/card", timeout=30).status_code == 204 and payer.get(f"{B}/me", timeout=30).json()["auto_topup"]["enabled"] is False)

# ---------------------------------------------------------------- admin
r = admin.post(f"{BASE}/api/v1/admin/billing/adjust", json={"user_id": payer_id, "amount": -50, "mode": "add", "note": "проверка"}, timeout=30)
check("admin debit never below zero", r.json()["balance"] == 0, r.text)
hist = admin.get(f"{BASE}/api/v1/admin/billing/history/{payer_id}", timeout=30).json()
check("admin sees the payer's history with the note", hist["entries"][0]["details"]["note"] == "проверка", str(hist["entries"][0]))

sys.exit(summary())
