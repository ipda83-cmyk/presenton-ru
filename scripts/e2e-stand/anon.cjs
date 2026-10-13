// An anonymous visitor sees the login form, never private content.
const puppeteer = require("puppeteer");
(async () => {
  const browser = await puppeteer.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox", "--disable-dev-shm-usage"], headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  const apiCalls = [];
  let failed = 0;
  page.on("response", (r) => { if (r.url().includes("/api/v1/studio") || r.url().includes("/api/v1/ppt")) apiCalls.push(r.status() + " " + r.url().replace("http://127.0.0.1", "")); });
  for (const path of ["/studio/storyboard", "/dashboard"]) {
    await page.goto("http://127.0.0.1" + path, { waitUntil: "networkidle2" });
    await page.waitForFunction(() => document.querySelectorAll('input[type="password"]').length > 0 || /Раскадровка|История/.test(document.body.innerText), { timeout: 60000 }).catch(() => {});
    const hasPassword = await page.$$eval('input[type="password"]', (e) => e.length);
    const leaks = await page.evaluate(() => /История|Ракурсы|Мои презентации/.test(document.body.innerText));
    const ok = hasPassword > 0 && !leaks;
    if (!ok) failed++;
    console.log(`${ok ? "PASS" : "FAIL"} anon ${path}: login form=${hasPassword > 0} private content visible=${leaks}`);
  }
  const answered = apiCalls.filter((call) => !call.startsWith("401"));
  if (answered.length) failed++;
  console.log(`${answered.length ? "FAIL" : "PASS"} anon: no data API answered (${JSON.stringify(answered)})`);
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
