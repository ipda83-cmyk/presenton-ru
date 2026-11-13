// Onboarding in the browser (headless Chromium inside the presenton-models
// stand after attack_models.py; copy next to puppeteer in
// /app/presentation-export). A fresh user sees the welcome, the tour, the
// First steps checklist and the editor tips; the administrator sees
// Admin → Onboarding. Screenshots: /tmp/e2e/onb-*.png
const puppeteer = require("puppeteer");

const BASE = "http://127.0.0.1";
const ADMIN = { username: "models-admin", password: "models-admin-pass-1" };
const USER = { username: `onb-${Date.now().toString(36)}`, password: "onb-user-pass-123" };
const results = [];
const check = (name, ok, detail = "") => {
  results.push([name, !!ok]);
  console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : `  [${detail}]`));
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function signedIn(browser, creds) {
  const page = await (await browser.createBrowserContext()).newPage();
  await page.setViewport({ width: 1440, height: 900 });
  await page.setCookie({ name: "NEXT_LOCALE", value: "ru", domain: "127.0.0.1" });
  await page.goto(BASE + "/api/v1/auth/status");
  const status = await page.evaluate(async (c) => {
    const r = await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c) });
    return r.status;
  }, creds);
  if (status !== 200) throw new Error(`login ${creds.username}: ${status}`);
  return page;
}

async function waitText(page, text, timeout = 40000) {
  return page
    .waitForFunction((value) => !document.querySelector(".brand-splash") && document.body.innerText.includes(value), { timeout }, text)
    .then(() => true)
    .catch(() => false);
}

async function clickText(page, text) {
  const handles = await page.$$("button, a");
  for (const handle of handles) {
    const label = (await handle.evaluate((el) => el.textContent || "")).trim();
    if (label === text) {
      await handle.click();
      return true;
    }
  }
  return false;
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox", "--disable-dev-shm-usage"], headless: true });
  const errors = [];

  const admin = await signedIn(browser, ADMIN);
  const created = await admin.evaluate(async (user) => (await fetch("/api/v1/admin/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(user) })).status, USER);
  check("the administrator creates a user", created === 201, String(created));

  const page = await signedIn(browser, USER);
  page.on("pageerror", (error) => errors.push(String(error)));

  // 1. Welcome
  await page.goto(BASE + "/dashboard", { waitUntil: "networkidle2" }).catch(() => {});
  check("the welcome opens on the first visit", await waitText(page, "Добро пожаловать в Kvant AI Studio"));
  check("it shows the start bonus", await waitText(page, "подарок на старт", 5000));
  await sleep(500);
  await page.screenshot({ path: "/tmp/e2e/onb-welcome.png" });

  // 2. Tour
  await clickText(page, "Сначала осмотрюсь");
  check("the tour starts", await waitText(page, "Новая презентация", 15000));
  await sleep(500);
  await page.screenshot({ path: "/tmp/e2e/onb-tour.png" });
  const steps = await page.evaluate(() => document.body.innerText.match(/1 из (\d)/)?.[1]);
  check("the tour has the dashboard steps", Number(steps) >= 4, String(steps));
  for (let i = 0; i < 6; i += 1) {
    if (!(await clickText(page, "Дальше"))) break;
    await sleep(300);
  }
  await page.screenshot({ path: "/tmp/e2e/onb-tour-last.png" });
  check("the tour ends with Help", await waitText(page, "пройти этот тур ещё раз", 5000));
  await clickText(page, "Готово");
  await sleep(800);

  // 3. Checklist
  check("the First steps checklist is on the dashboard", await waitText(page, "Первые шаги", 10000));
  const progress = await page.evaluate(() => document.body.innerText.match(/(\d) из (\d)/)?.slice(1).map(Number));
  check("nothing is done yet, six steps with billing", progress && progress[0] === 0 && progress[1] === 6, JSON.stringify(progress));
  await page.screenshot({ path: "/tmp/e2e/onb-checklist.png", fullPage: false });

  // 4. Seen once
  await page.reload({ waitUntil: "networkidle2" });
  await waitText(page, "Первые шаги", 15000);
  await sleep(1500);
  const again = await page.evaluate(() => document.body.innerText);
  check("no welcome or tour on the next visit", !again.includes("Добро пожаловать в Kvant") && !again.includes("Дальше"));

  // 5. A presentation: the checklist ticks it; the editor shows its tips
  const generated = await page.evaluate(async () => {
    const r = await fetch("/api/v1/ppt/presentation/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: "Онбординг", n_slides: 2, language: "Russian" }) });
    return { status: r.status, body: await r.json().catch(() => ({})) };
  });
  check("the user makes a presentation", generated.status === 200, JSON.stringify(generated).slice(0, 200));
  await page.goto(BASE + "/dashboard", { waitUntil: "networkidle2" }).catch(() => {});
  await waitText(page, "Первые шаги", 15000);
  await sleep(1000);
  const ticked = await page.evaluate(() => document.body.innerText.match(/(\d) из (\d)/)?.[1]);
  // The API also exports a PPTX by default: «create» and «download» are both done.
  check("the checklist ticks the presentation and the download", ticked === "2", String(ticked));

  if (generated.body.presentation_id) {
    await page.goto(`${BASE}/presentation?id=${generated.body.presentation_id}`, { waitUntil: "networkidle2" }).catch(() => {});
    check("the editor shows the export tip", await waitText(page, "Скачать презентацию", 30000));
    await sleep(500);
    await page.screenshot({ path: "/tmp/e2e/onb-tip.png" });
    await clickText(page, "Понятно");
    check("then the AI assistant tip", await waitText(page, "ИИ-помощник", 10000));
    await clickText(page, "Понятно");
    await sleep(800);
    await page.reload({ waitUntil: "networkidle2" });
    await sleep(3000);
    const tips = await page.evaluate(() => document.body.innerText);
    check("closed tips stay closed", !tips.includes("Понятно"));
  }

  // 6. Admin → Onboarding
  admin.on("pageerror", (error) => errors.push(String(error)));
  await admin.goto(BASE + "/admin", { waitUntil: "networkidle2" }).catch(() => {});
  await waitText(admin, "Онбординг");
  const tabs = await admin.$$("button[role=tab]");
  for (const tab of tabs) {
    if ((await tab.evaluate((el) => el.textContent)).trim() === "Онбординг") await tab.click();
  }
  check("Admin → Onboarding shows the results", await waitText(admin, "сделали презентацию", 15000));
  const stats = await admin.evaluate(() => document.body.innerText.match(/(\d+)\s*\n?\s*новых за 30 дней/)?.[1]);
  check("the new user is counted", Number(stats) >= 1, String(stats));
  await sleep(500);
  await admin.screenshot({ path: "/tmp/e2e/onb-admin.png", fullPage: true });
  await admin.goto(BASE + "/dashboard", { waitUntil: "networkidle2" }).catch(() => {});
  await sleep(2500);
  check("administrators do not get the welcome", !(await admin.evaluate(() => document.body.innerText.includes("Добро пожаловать в Kvant"))));

  check("no page errors", errors.length === 0, errors.join(" | ").slice(0, 300));
  await browser.close();
  const failed = results.filter((r) => !r[1]);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
