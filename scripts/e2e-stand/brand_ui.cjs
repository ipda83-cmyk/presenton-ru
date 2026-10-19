// Kvant AI Studio branding in the browser (headless Chromium inside a stand
// container, e.g. presenton-models after attack_models.py): splash frames,
// main pages, no "Presenton" where it is our product, no Presenton purple in
// the interface. Screenshots: /tmp/e2e/brand-*.png
const puppeteer = require("puppeteer");

const BASE = "http://127.0.0.1";
const ADMIN = { username: process.env.BRAND_USER || "models-admin", password: process.env.BRAND_PASS || "models-admin-pass-1" };
// "Presenton" may stay only where it names Presenton Cloud, its community or the project we are built on.
const ALLOWED = /Presenton Cloud|built on the open-source Presenton|основан на открытом проекте Presenton|Presenton \(Apache/;
const PURPLES = ["rgb(122, 90, 248)", "rgb(124, 81, 248)", "rgb(81, 70, 229)", "rgb(81, 65, 229)", "rgb(124, 58, 237)", "rgb(105, 65, 198)"];
const results = [];
const check = (name, ok, detail = "") => {
  results.push([name, !!ok, detail]);
  console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : `  [${detail}]`));
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function purpleElements(page) {
  return page.evaluate((purples) => {
    const found = [];
    for (const el of document.querySelectorAll("body *")) {
      if (el.closest("[data-slide-content], .slide-container, svg foreignObject")) continue;
      const style = getComputedStyle(el);
      for (const prop of ["color", "backgroundColor", "borderTopColor", "fill", "stroke"]) {
        if (purples.includes(style[prop])) {
          found.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 40)} ${prop}`);
          break;
        }
      }
    }
    return found.slice(0, 5);
  }, PURPLES);
}

async function presentonMentions(page) {
  return page.evaluate((allowed) => {
    const text = document.body.innerText + " " + document.title;
    return text
      .split(/\n+/)
      .filter((line) => line.includes("Presenton") && !new RegExp(allowed).test(line))
      .slice(0, 3);
  }, ALLOWED.source);
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox", "--disable-dev-shm-usage"], headless: true });
  const errors = [];

  // ---- the splash, frame by frame (signed out: the sign-in gate shows it)
  const splash = await (await browser.createBrowserContext()).newPage();
  await splash.setViewport({ width: 1280, height: 800 });
  await splash.setCookie({ name: "NEXT_LOCALE", value: "ru", domain: "127.0.0.1" });
  const started = Date.now();
  void splash.goto(BASE + "/", { waitUntil: "domcontentloaded" }).catch(() => {});
  await splash.waitForSelector(".brand-splash", { timeout: 15000 }).catch(() => {});
  for (const at of [400, 1000, 1500, 2600]) {
    await sleep(Math.max(0, at - (Date.now() - started)));
    await splash.screenshot({ path: `/tmp/e2e/brand-splash-${at}.png` }).catch(() => {});
  }
  const splashState = await splash.evaluate(() => {
    const el = document.querySelector(".brand-splash");
    return el ? { name: el.querySelector(".brand-splash-name")?.textContent, status: el.querySelector(".brand-splash-status")?.textContent } : null;
  }).catch(() => null);
  check("the splash shows the new name", splashState?.name === "Kvant AI Studio", JSON.stringify(splashState));
  check("the splash status is in Russian", /Готовим/.test(splashState?.status ?? ""), JSON.stringify(splashState));

  // ---- the main pages
  const page = await (await browser.createBrowserContext()).newPage();
  page.on("pageerror", (error) => errors.push(String(error)));
  await page.setViewport({ width: 1440, height: 900 });
  await page.setCookie({ name: "NEXT_LOCALE", value: "ru", domain: "127.0.0.1" });
  await page.goto(BASE + "/api/v1/auth/status");
  const login = await page.evaluate(async (creds) => (await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(creds) })).status, ADMIN);
  check("admin signs in", login === 200, String(login));

  for (const [name, path] of [
    ["dashboard", "/dashboard"],
    ["upload", "/upload"],
    ["studio", "/studio"],
    ["admin", "/admin"],
    ["billing", "/billing"],
    ["settings", "/settings"],
    ["help", "/help"],
  ]) {
    await page.goto(BASE + path, { waitUntil: "networkidle2" }).catch(() => {});
    await page
      .waitForFunction(
        () => !document.querySelector(".brand-splash, .configuration-loader") && document.body.innerText.trim().length > 120,
        { timeout: 30000 },
      )
      .catch(() => {});
    await sleep(800);
    await page.screenshot({ path: `/tmp/e2e/brand-${name}.png` });
    const mentions = await presentonMentions(page);
    check(`${name}: our product is called Kvant AI Studio`, mentions.length === 0, JSON.stringify(mentions));
    const purple = await purpleElements(page);
    check(`${name}: no Presenton purple`, purple.length === 0, JSON.stringify(purple));
    if (name === "dashboard") {
      check("the tab title", /Kvant AI Studio/.test(await page.title()), await page.title());
      check("the logo mark is there", (await page.$$("svg[aria-label='Kvant AI Studio'], [aria-label='Kvant AI Studio']")).length > 0);
    }
  }
  const icon = await page.evaluate(async () => (await fetch("/favicon.ico")).status);
  check("favicon is served", icon === 200, String(icon));

  check("no page errors", errors.length === 0, errors.join(" | ").slice(0, 300));
  await browser.close();
  const failed = results.filter((r) => !r[1]);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
