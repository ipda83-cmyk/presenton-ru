// Admin → Help in the browser (headless Chromium inside the presenton-models
// stand after attack_models.py): the editor starts from the built-in help,
// a section is edited and saved, users see it on /help with rendered Markdown;
// no Discord/GitHub on the dashboard. Screenshots: /tmp/e2e/help-*.png
const puppeteer = require("puppeteer");

const BASE = "http://127.0.0.1";
const ADMIN = { username: "models-admin", password: "models-admin-pass-1" };
const USER = { username: "models-user", password: "models-user-pass-1" };
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
  await page.evaluate(async (c) => {
    await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c) });
  }, creds);
  return page;
}

async function ready(page, text) {
  await page
    .waitForFunction((t) => !document.querySelector(".brand-splash") && document.body.innerText.includes(t), { timeout: 40000 }, text)
    .catch(() => {});
  await sleep(500);
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox", "--disable-dev-shm-usage"], headless: true });
  const errors = [];
  const admin = await signedIn(browser, ADMIN);
  admin.on("pageerror", (error) => errors.push(String(error)));

  await admin.evaluate(() => fetch("/api/v1/admin/help", { method: "DELETE" }));
  await admin.goto(BASE + "/admin", { waitUntil: "networkidle2" }).catch(() => {});
  await ready(admin, "Помощь");
  const tab = await admin.$$("button[role=tab]");
  for (const button of tab) {
    if ((await button.evaluate((el) => el.textContent)).trim() === "Помощь") await button.click();
  }
  await ready(admin, "Раздел «Помощь»");
  const titles = await admin.evaluate(() => document.body.innerText);
  check("the editor starts from the built-in help", titles.includes("Быстрый старт") && titles.includes("встроенная справка"), titles.slice(0, 200));
  await admin.screenshot({ path: "/tmp/e2e/help-admin.png", fullPage: true });

  // Add a section, fill it and save.
  const buttons = await admin.$$("button");
  for (const button of buttons) {
    if ((await button.evaluate((el) => el.textContent)).includes("Добавить раздел")) await button.click();
  }
  await sleep(300);
  const titleInput = await admin.$("input[placeholder^='Например']");
  await titleInput.type("Как оплатить");
  await admin.type("textarea", "## Оплата картой\n\n**Важно:** баланс пополняется сразу.\n\n- шаг один\n- шаг два");
  await admin.screenshot({ path: "/tmp/e2e/help-editor.png", fullPage: true });
  for (const button of await admin.$$("button")) {
    if ((await button.evaluate((el) => el.textContent)).trim() === "Сохранить") await button.click();
  }
  await ready(admin, "Сохранено");
  const stored = await admin.evaluate(async () => (await fetch("/api/v1/help")).json());
  check("the administrator saves the edited help", stored.custom && stored.sections.some((s) => s.title === "Как оплатить"),
    JSON.stringify(stored).slice(0, 200));

  // Users see it with Markdown rendered.
  const user = await signedIn(browser, USER);
  user.on("pageerror", (error) => errors.push(String(error)));
  await user.goto(BASE + "/help", { waitUntil: "networkidle2" }).catch(() => {});
  await ready(user, "Как оплатить");
  await sleep(800);
  const rendered = await user.evaluate(() => ({
    h2: [...document.querySelectorAll("h2")].map((el) => el.textContent),
    strong: [...document.querySelectorAll("main strong")].map((el) => el.textContent),
    items: document.querySelectorAll("main .prose li").length,
  }));
  check("users see the section", rendered.h2.includes("Как оплатить"), JSON.stringify(rendered));
  check("Markdown is rendered", rendered.strong.includes("Важно:") && rendered.items >= 2 && rendered.h2.includes("Оплата картой"), JSON.stringify(rendered));
  await user.screenshot({ path: "/tmp/e2e/help-user.png", fullPage: true });

  await admin.goto(BASE + "/dashboard", { waitUntil: "networkidle2" }).catch(() => {});
  await ready(admin, "Настройки");
  const html = (await admin.content()).toLowerCase();
  check("no Discord or GitHub on the dashboard", !html.includes("discord") && !html.includes("github"));
  await admin.screenshot({ path: "/tmp/e2e/help-dashboard.png" });

  await admin.evaluate(() => fetch("/api/v1/admin/help", { method: "DELETE" }));
  check("no page errors", errors.length === 0, errors.join(" | ").slice(0, 300));
  await browser.close();
  const failed = results.filter((r) => !r[1]);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
