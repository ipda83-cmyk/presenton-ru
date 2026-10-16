// Admin → Models and the Studio with catalog models, in headless Chromium inside
// the presenton-models container (after attack_models.py). Screenshots: /tmp/e2e/*.png
const puppeteer = require("puppeteer");

const BASE = "http://127.0.0.1";
const ADMIN = { username: "models-admin", password: "models-admin-pass-1" };
const USER = { username: "models-user", password: "models-user-pass-1" };
const results = [];
const check = (name, ok, detail = "") => {
  results.push([name, !!ok, detail]);
  console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : `  [${detail}]`));
};
const text = (page) => page.evaluate(() => document.body.innerText.replace(/[  ]/g, " "));
const waitText = (page, source, timeout = 60000) =>
  page
    .waitForFunction((src) => new RegExp(src).test(document.body.innerText.replace(/[  ]/g, " ")), { timeout }, source)
    .then(() => true)
    .catch(() => false);
const login = (page, creds) =>
  page.evaluate(async (c) => (await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c) })).status, creds);
// A real mouse click (Radix tabs switch on mousedown), on the first element whose text matches.
const clickText = async (page, source, selector = "button,a,[role=tab]") => {
  const handles = await page.$$(selector);
  for (const handle of handles) {
    const label = await handle.evaluate((e) => (e.innerText || "").trim());
    if (new RegExp(source).test(label)) {
      await handle.click();
      return true;
    }
  }
  return false;
};

(async () => {
  const browser = await puppeteer.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox", "--disable-dev-shm-usage"], headless: true });
  const errors = [];

  const admin = await (await browser.createBrowserContext()).newPage();
  admin.on("pageerror", (error) => errors.push(String(error)));
  await admin.setViewport({ width: 1440, height: 1000 });
  await admin.setCookie({ name: "NEXT_LOCALE", value: "ru", domain: "127.0.0.1" });
  await admin.goto(BASE + "/api/v1/auth/status");
  check("admin signs in", (await login(admin, ADMIN)) === 200);
  await admin.goto(BASE + "/admin", { waitUntil: "networkidle2" });
  await waitText(admin, "Балансы");
  check("the Models tab is there", await clickText(admin, "^Модели$"));
  check("the tab lists the models", await waitText(admin, "Модели: видят пользователи"));
  const adminText = await text(admin);
  check("the catalog source is shown", /Каталог arckep: 37 моделей|Встроенный каталог/.test(adminText), adminText.slice(0, 300));
  check("model names are editable", (await admin.$$eval("input[aria-label='Название для пользователей']", (els) => els.map((e) => e.value))).includes("FLUX Про"));
  await admin.screenshot({ path: "/tmp/e2e/admin-models.png", fullPage: true });
  check("details open", await clickText(admin, "Цены и детали"));
  check("prices per option", await waitText(admin, "Себестоимость"));
  await admin.screenshot({ path: "/tmp/e2e/admin-models-details.png", fullPage: true });

  const user = await (await browser.createBrowserContext()).newPage();
  user.on("pageerror", (error) => errors.push(String(error)));
  await user.setViewport({ width: 1440, height: 1000 });
  await user.setCookie({ name: "NEXT_LOCALE", value: "ru", domain: "127.0.0.1" });
  await user.goto(BASE + "/api/v1/auth/status");
  check("user signs in", (await login(user, USER)) === 200);
  await user.goto(BASE + "/studio", { waitUntil: "networkidle2" });
  check("the Studio opens", await waitText(user, "Сгенерировать"));
  await waitText(user, "Сгенерировать\\s*·\\s*\\d+\\s*₽", 30000);
  const buttons = await user.$$eval("button", (els) => els.map((e) => e.innerText.replace(/[  ]/g, " ").trim()));
  const button = buttons.find((label) => label.startsWith("Сгенерировать")) ?? "";
  check("the price is on the button", /^Сгенерировать\s*·\s*\d+\s*₽$/.test(button), JSON.stringify(button));
  const options = await user.$$eval("select option, [role=option]", (els) => els.map((e) => e.textContent.trim()));
  check("only chosen models are offered", !options.some((o) => /Recraft/.test(o)), JSON.stringify(options));
  await user.screenshot({ path: "/tmp/e2e/studio-models.png", fullPage: true });

  check("no page errors", errors.length === 0, errors.join(" | ").slice(0, 400));
  await browser.close();
  const failed = results.filter((r) => !r[1]);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
