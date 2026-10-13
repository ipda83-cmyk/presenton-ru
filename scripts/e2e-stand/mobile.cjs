// Phone width (375 px): every page renders and has no horizontal scroll.
const puppeteer = require("puppeteer");
const fs = require("fs");
const creds = JSON.parse(fs.readFileSync("/tmp/e2e/accounts.json", "utf8")).user;
(async () => {
  const browser = await puppeteer.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox", "--disable-dev-shm-usage"], headless: true });
  const page = await browser.newPage();
  await page.goto("http://127.0.0.1/", { waitUntil: "domcontentloaded" });
  await page.evaluate(async (c) => fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c) }), creds);
  await page.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true, deviceScaleFactor: 1 });
  let failed = 0;
  for (const [path, name] of [["/studio", "studio"], ["/studio/brush", "brush"], ["/studio/reference", "reference"], ["/studio/storyboard", "storyboard"], ["/upload", "upload"], ["/dashboard", "dashboard"]]) {
    await page.goto("http://127.0.0.1" + path, { waitUntil: "networkidle2" });
    const ready = await page.waitForFunction(
      () => !document.querySelector(".configuration-loader") && !document.querySelector(".presenton-splash-loader:not([hidden])") && document.body.innerText.trim().length > 60,
      { timeout: 60000 },
    ).then(() => true).catch(() => false);
    await new Promise((r) => setTimeout(r, 1000));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const wide = await page.evaluate(() => [...document.querySelectorAll("body *")].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > window.innerWidth + 1; }).slice(0, 4).map((e) => e.tagName + "." + String(e.className).slice(0, 50)));
    const ok = ready && overflow <= 1;
    if (!ok) failed++;
    console.log((ok ? "PASS " : "FAIL ") + `mobile ${path}: rendered=${ready} overflow=${overflow}px` + (wide.length ? ` wide=${JSON.stringify(wide)}` : ""));
    await page.screenshot({ path: `/tmp/e2e/m-${name}.png`, fullPage: true });
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
