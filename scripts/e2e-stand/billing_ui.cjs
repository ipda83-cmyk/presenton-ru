// Billing in the browser (headless Chromium inside the stand): prices on buttons,
// balance in the bars, the "not enough funds" dialog, a top-up through the fake
// YooKassa page and back, auto top-up, the admin tab and settings, phone width.
const puppeteer = require("puppeteer");
const fs = require("fs");

const BASE = "http://127.0.0.1";
const accounts = JSON.parse(fs.readFileSync("/tmp/e2e/accounts.json", "utf8"));
const results = [];
const check = (name, ok, detail = "") => {
  results.push([name, !!ok, detail]);
  console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : `  [${detail}]`));
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// Amounts use no-break spaces ("1 000 ₽"): compare with plain spaces.
const text = (page) => page.evaluate(() => document.body.innerText.replace(/[  ]/g, " "));
const waitText = (page, source, timeout = 60000) =>
  page
    .waitForFunction((src) => new RegExp(src).test(document.body.innerText.replace(/[  ]/g, " ")), { timeout }, source)
    .then(() => true)
    .catch(() => false);
const api = (page, path, method = "GET", body) =>
  page.evaluate(
    async (p, m, b) => {
      const response = await fetch(p, { method: m, headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : undefined });
      return { status: response.status, body: await response.json().catch(() => null) };
    },
    path,
    method,
    body,
  );
const clickText = (page, source, selector = "button,a") =>
  page.evaluate(
    (src, sel) => {
      const re = new RegExp(src);
      const el = [...document.querySelectorAll(sel)].find((e) => re.test((e.innerText || "").trim()) || re.test(e.getAttribute("aria-label") || ""));
      if (!el) return false;
      el.click();
      return true;
    },
    source,
    selector,
  );
const rendered = (page) =>
  page.waitForFunction(() => !document.querySelector(".configuration-loader") && document.body.innerText.trim().length > 60, { timeout: 60000 }).catch(() => {});

(async () => {
  const browser = await puppeteer.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox", "--disable-dev-shm-usage"], headless: true });
  const errors = [];

  // ---- administrator creates a fresh payer
  const adminContext = await browser.createBrowserContext();
  const admin = await adminContext.newPage();
  await admin.setViewport({ width: 1366, height: 900 });
  await admin.goto(BASE + "/api/v1/auth/status", { waitUntil: "domcontentloaded" });
  await api(admin, "/api/v1/auth/login", "POST", accounts.admin);
  const username = `ui-payer-${Date.now()}`;
  const password = `Pw-${Math.random().toString(36).slice(2)}-${Date.now()}`;
  const created = await api(admin, "/api/v1/admin/users", "POST", { username, password });
  check("admin created a payer", created.status === 201, JSON.stringify(created));
  const payerId = created.body.id;

  // ---- payer: prices and balance
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewport({ width: 1366, height: 900 });
  await page.goto(BASE + "/api/v1/auth/status", { waitUntil: "domcontentloaded" });
  await page.setCookie({ name: "NEXT_LOCALE", value: "ru", url: BASE });
  check("payer login", (await api(page, "/api/v1/auth/login", "POST", { username, password })).status === 200);

  await page.goto(BASE + "/studio", { waitUntil: "networkidle2" });
  await rendered(page);
  check("generate button shows the price", await waitText(page, "Сгенерировать · 12 ₽"), (await text(page)).slice(0, 300));
  check("top bar: balance and «Пополнить»", (await waitText(page, "100 ₽")) && /Пополнить/.test(await text(page)));
  check("sidebar: balance link", (await page.$$('a[href="/billing"][aria-label^="Баланс:"]')).length >= 1);
  await page.type("textarea", "Ракета на старте");
  await clickText(page, "^Сгенерировать");
  check("balance in the bars updates after a paid request", await waitText(page, "88 ₽"), "");

  // ---- not enough money -> dialog with a top-up link
  await api(admin, "/api/v1/admin/billing/adjust", "POST", { user_id: payerId, amount: 0, mode: "set" });
  await clickText(page, "^Сгенерировать");
  const dialog = await page.waitForSelector('[role="dialog"]', { timeout: 30000 }).catch(() => null);
  const dialogText = dialog ? await dialog.evaluate((el) => el.innerText) : "";
  check("402 opens «Недостаточно средств» with amounts", /Недостаточно средств/.test(dialogText) && /нужно 12 ₽, на балансе 0 ₽/.test(dialogText), dialogText);
  const topLink = await page.$('[role="dialog"] a[href="/billing#topup"][target="_blank"]');
  check("dialog link opens the billing page in a new tab", !!topLink);
  await page.screenshot({ path: "/tmp/e2e/shot-billing-dialog.png" });
  await page.keyboard.press("Escape");

  // ---- top up through the YooKassa page and back
  await page.goto(BASE + "/billing", { waitUntil: "networkidle2" });
  await rendered(page);
  check("billing page: zero balance and prices", (await waitText(page, "0 ₽")) && /10 ₽ за слайд/.test(await text(page)), (await text(page)).slice(0, 400));
  await clickText(page, "^1.000.₽", '[role="radio"]');
  await page.type("#receipt-email", "ui@example.com");
  await clickText(page, "^Сохранить карту", "label");
  await page.evaluate(() => {
    const box = [...document.querySelectorAll("label")].find((label) => /Согласен на автоматические списания/.test(label.innerText));
    box?.querySelector("input")?.click();
  });
  check("offer link next to the consent", (await page.$('a[href="https://example.com/offer"]')) !== null);
  await page.screenshot({ path: "/tmp/e2e/shot-billing-topup.png", fullPage: true });
  await Promise.all([page.waitForNavigation({ timeout: 60000 }).catch(() => {}), clickText(page, "^Перейти к оплате 1.000.₽")]);
  check("redirected to the (fake) YooKassa page", page.url().includes("/yookassa/pay/"), page.url());
  await Promise.all([page.waitForNavigation({ timeout: 60000 }).catch(() => {}), page.click("#pay")]);
  check("back on /billing after paying", page.url().startsWith(BASE + "/billing"), page.url());
  check("banner: topped up by 1 000 ₽", await waitText(page, "Баланс пополнен на 1.000 ₽", 40000), (await text(page)).slice(0, 300));
  check("balance shows 1 000 ₽", await waitText(page, "1.000 ₽"));
  check("history lists the top-up", await waitText(page, "Пополнение"));
  check("saved card is shown", await waitText(page, "MasterCard •••• 4477"));
  await page.evaluate(() => {
    const label = [...document.querySelectorAll("label")].find((item) => /Пополнять автоматически/.test(item.innerText));
    label?.querySelector("input")?.click();
  });
  await clickText(page, "^Сохранить$");
  check("auto top-up saved", await waitText(page, "Сохранено"));
  await page.screenshot({ path: "/tmp/e2e/shot-billing-page.png", fullPage: true });

  // ---- phone width
  await page.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true });
  await page.goto(BASE + "/billing", { waitUntil: "networkidle2" });
  await rendered(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check("billing page fits a phone", overflow <= 1, `overflow=${overflow}`);
  await page.screenshot({ path: "/tmp/e2e/shot-billing-mobile.png", fullPage: true });

  // ---- administrator: balances tab and settings
  await admin.goto(BASE + "/admin", { waitUntil: "networkidle2" });
  await rendered(admin);
  const tabs = await admin.$$('[role="tab"]');
  let billingTab = null;
  for (const tab of tabs) if ((await tab.evaluate((el) => el.innerText.trim())) === "Балансы") billingTab = tab;
  check("admin: «Балансы» tab exists", !!billingTab);
  if (billingTab) await billingTab.click();
  const listed = await admin
    .waitForFunction(
      (name) => {
        const panel = document.querySelector('[role="tabpanel"][data-state="active"]');
        return !!panel && panel.innerText.includes(name) && /1.000.₽/.test(panel.innerText) && /Начислить или списать/.test(panel.innerText);
      },
      { timeout: 30000 },
      username,
    )
    .then(() => true)
    .catch(() => false);
  check("admin: balances tab lists the payer with 1 000 ₽", listed);
  await admin.screenshot({ path: "/tmp/e2e/shot-admin-billing.png", fullPage: true });
  await admin.goto(BASE + "/settings?section=billing", { waitUntil: "networkidle2" });
  await rendered(admin);
  check("settings: payments section with the webhook URL", await waitText(admin, "/api/v1/billing/yookassa/webhook"), (await text(admin)).slice(0, 300));
  await admin.screenshot({ path: "/tmp/e2e/shot-settings-billing.png", fullPage: true });

  check("no uncaught page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
  await browser.close();
  const failed = results.filter((item) => !item[1]);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((error) => {
  console.error("CRASH", error);
  process.exit(2);
});
