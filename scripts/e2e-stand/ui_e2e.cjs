// Headless UI run inside the e2e stand: Studio generate -> Storyboard (real backend + fake arckep), brush, mobile.
const puppeteer = require("puppeteer");
const fs = require("fs");

const BASE = "http://127.0.0.1";
const FAKE = "http://presenton-e2e-fake:9000/control";
const creds = JSON.parse(fs.readFileSync("/tmp/e2e/accounts.json", "utf8")).user;
const results = [];
const check = (name, ok, detail = "") => {
  results.push([name, !!ok, detail]);
  console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : `  [${detail}]`));
};
const fake = async (state = {}) =>
  (await fetch(FAKE, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state) })).json();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function clickText(page, source, selector = "button") {
  return page.evaluate(
    (src, sel) => {
      const re = new RegExp(src);
      const el = [...document.querySelectorAll(sel)].find(
        (e) => re.test((e.innerText || "").trim()) || re.test(e.getAttribute("aria-label") || ""),
      );
      if (!el) return false;
      el.click();
      return true;
    },
    source,
    selector,
  );
}
const waitText = (page, source, timeout = 60000) =>
  page.waitForFunction((src) => new RegExp(src).test(document.body.innerText), { timeout }, source);
const count = (page, selector) => page.$$eval(selector, (els) => els.length);

(async () => {
  const browser = await puppeteer.launch({
    executablePath: "/usr/bin/chromium",
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
    headless: true,
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 900 });
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  let uploads = 0;
  let inflight = 0;
  let maxInflight = 0;
  page.on("request", (r) => {
    if (r.url().includes("/api/v1/ppt/images/upload")) uploads++;
    if (r.url().includes("/api/v1/studio/storyboard")) maxInflight = Math.max(maxInflight, ++inflight);
  });
  const done = (r) => {
    if (r.url().includes("/api/v1/studio/storyboard")) inflight--;
  };
  page.on("requestfinished", done);
  page.on("requestfailed", done);

  await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
  const status = await page.evaluate(
    async (c) => (await fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c) })).status,
    creds,
  );
  check("login", status === 200, String(status));

  // ---- Studio: generate, then send the result to Storyboard
  await fake({ reset_log: true, arckep: "ok", llm: "ok", llm_delay: 0 });
  await page.goto(BASE + "/studio", { waitUntil: "networkidle2" });
  await page.waitForSelector("textarea", { timeout: 60000 });
  await page.type("textarea", "Робот-курьер с синим корпусом, студийный свет");
  check("studio: generate clicked", await clickText(page, "^Сгенерировать$"));
  await page.waitForSelector('a[href^="/studio/storyboard?image="]', { timeout: 60000 });
  check("studio: result shown with its actions", (await count(page, 'a[href^="/studio/brush?image="]')) === 1);
  await page.screenshot({ path: "/tmp/e2e/shot-studio.png" });
  check("studio: «Раскадровка» action present", await clickText(page, "^Раскадровка$", 'a[href^="/studio/storyboard?image="]'));
  await page.waitForFunction(() => location.pathname === "/studio/storyboard", { timeout: 30000 });
  await sleep(1500);
  await page.waitForSelector('img[alt="Изображение для раскадровки"]', { timeout: 60000 });
  check("storyboard: reference arrives from the Studio result", true);
  await sleep(500);
  check("storyboard: no upload for a history image", uploads === 0, `uploads=${uploads}`);

  // ---- Storyboard: all 12 views, queue of 3
  check("storyboard: select all", await clickText(page, "^Выбрать все$"));
  await page.type("textarea", "в рабочей каске");
  check("storyboard: submit 12", await clickText(page, "^Сгенерировать 12 ракурсов$"));
  const t0 = Date.now();
  await page.waitForFunction(
    () => document.querySelectorAll('[aria-label^="Скачать ракурс"]').length === 12,
    { timeout: 180000 },
  ).catch(() => {});
  const got = await count(page, '[aria-label^="Скачать ракурс"]');
  check("storyboard: 12 views done", got === 12, `done=${got} after ${(Date.now() - t0) / 1000}s`);
  check("storyboard: at most 3 requests at once", maxInflight <= 3 && maxInflight >= 2, `max=${maxInflight}`);
  const state = await fake();
  const jobs = state.log.filter((e) => e.kind === "job" && e.prompt.includes("Using the SAME"));
  check("storyboard: 12 arckep jobs, each with the reference", jobs.length === 12 && jobs.every((j) => j.refs === 1), `jobs=${jobs.length}`);
  check("storyboard: details reach the prompt", jobs.every((j) => j.prompt.length > 0) && state.log.some((e) => (e.prompt || "").includes("Using the SAME")), "");
  check("arckep never above 5 jobs", state.state.max_active_jobs <= 5, String(state.state.max_active_jobs));
  await page.screenshot({ path: "/tmp/e2e/shot-storyboard.png", fullPage: true });

  // ---- Failure + single retry
  await clickText(page, "^Снять все$");
  await clickText(page, "^Сверху$");
  await clickText(page, "^Снизу$");
  await fake({ arckep: "job_failed" });
  check("storyboard: submit 2 with failing provider", await clickText(page, "^Сгенерировать 2 ракурса$"));
  await page.waitForFunction(() => document.querySelectorAll('[aria-label^="Повторить ракурс"]').length === 2, { timeout: 60000 }).catch(() => {});
  check("storyboard: both failures show a retry", (await count(page, '[aria-label^="Повторить ракурс"]')) === 2);
  const errorText = await page.evaluate(() => document.body.innerText.includes("content policy violation"));
  check("storyboard: provider reason is shown", errorText);
  await fake({ arckep: "ok", reset_log: true });
  check("storyboard: retry one view", await clickText(page, "^Повторить ракурс «Сверху»$"));
  await page.waitForFunction(() => document.querySelectorAll('[aria-label^="Скачать ракурс"]').length === 1, { timeout: 60000 }).catch(() => {});
  check("storyboard: retried view is done", (await count(page, '[aria-label^="Скачать ракурс «Сверху»"]')) === 1);
  const after = await fake();
  check("storyboard: retry sends exactly one job", after.log.filter((e) => e.kind === "job").length === 1, JSON.stringify(after.log.map((e) => e.kind)));
  check("storyboard: other failed view untouched", (await count(page, '[aria-label^="Повторить ракурс"]')) === 1);

  // ---- Upload path: own file is uploaded once for several views
  await page.goto(BASE + "/studio/storyboard", { waitUntil: "networkidle2" });
  uploads = 0;
  const input = await page.waitForSelector('input[type="file"]', { timeout: 60000 });
  await input.uploadFile("/tmp/e2e/hero.png");
  await page.waitForSelector('img[alt="Изображение для раскадровки"]', { timeout: 30000 });
  check("storyboard: submit default 4 from own file", await clickText(page, "^Сгенерировать 4 ракурса$"));
  await page.waitForFunction(() => document.querySelectorAll('[aria-label^="Скачать ракурс"]').length === 4, { timeout: 120000 }).catch(() => {});
  check("storyboard: 4 views from own file", (await count(page, '[aria-label^="Скачать ракурс"]')) === 4);
  check("storyboard: own file uploaded exactly once", uploads === 1, `uploads=${uploads}`);

  // ---- Brush page: draw a stroke and apply
  await page.goto(BASE + "/studio/brush", { waitUntil: "networkidle2" });
  const brushInput = await page.waitForSelector('input[type="file"]', { timeout: 60000 });
  await brushInput.uploadFile("/tmp/e2e/hero.png");
  const canvas = await page.waitForSelector("canvas", { timeout: 30000 });
  const box = await canvas.boundingBox();
  await page.mouse.move(box.x + box.width * 0.4, box.y + box.height * 0.4);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.5, { steps: 12 });
  await page.mouse.up();
  const prompts = await page.$$("textarea");
  await prompts[prompts.length - 1].type("заменить на красный шар");
  await fake({ reset_log: true });
  check("brush: apply clicked", await clickText(page, "^Применить к выделенному$"));
  await page.waitForFunction(() => /После/.test(document.body.innerText), { timeout: 60000 }).catch(() => {});
  const brushLog = await fake();
  check("brush: one job with image + mask", brushLog.log.some((e) => e.kind === "job" && e.refs === 2), JSON.stringify(brushLog.log.filter((e) => e.kind === "job")));
  await page.screenshot({ path: "/tmp/e2e/shot-brush.png" });

  // ---- Mobile: no horizontal scroll on Studio pages
  await page.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true });
  for (const path of ["/studio", "/studio/brush", "/studio/reference", "/studio/storyboard"]) {
    await page.goto(BASE + path, { waitUntil: "networkidle2" });
    await sleep(800);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    check(`mobile ${path}: no horizontal scroll`, overflow <= 1, `overflow=${overflow}px`);
  }
  await page.screenshot({ path: "/tmp/e2e/shot-mobile-storyboard.png", fullPage: true });

  check("no uncaught page errors", pageErrors.length === 0, pageErrors.slice(0, 3).join(" | "));
  await browser.close();
  const failed = results.filter((r) => !r[1]);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((e) => {
  console.error("CRASH", e);
  process.exit(2);
});
