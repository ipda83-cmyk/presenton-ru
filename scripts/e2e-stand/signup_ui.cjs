// Sign-up pages in the browser (headless Chromium inside the presenton-signup
// stand after attack_signup.py; copy next to puppeteer in
// /app/presentation-export). Screenshots: /tmp/e2e/signup-*.png
const puppeteer = require("puppeteer");

const BASE = "http://127.0.0.1";
const ADMIN = { username: "signup-admin", password: "signup-admin-pass-1" };
const results = [];
const check = (name, ok, detail = "") => {
  results.push([name, !!ok]);
  console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : `  [${detail}]`));
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fresh(browser) {
  const page = await (await browser.createBrowserContext()).newPage();
  await page.setViewport({ width: 1280, height: 860 });
  await page.setCookie({ name: "NEXT_LOCALE", value: "ru", domain: "127.0.0.1" });
  return page;
}

async function waitText(page, text, timeout = 30000) {
  return page
    .waitForFunction((value) => !document.querySelector(".brand-splash") && document.body.innerText.includes(value), { timeout }, text)
    .then(() => true)
    .catch(() => false);
}

(async () => {
  const browser = await puppeteer.launch({ executablePath: "/usr/bin/chromium", args: ["--no-sandbox", "--disable-dev-shm-usage"], headless: true });
  const errors = [];

  // Sign-in shows the new links once sign-up is open.
  const visitor = await fresh(browser);
  visitor.on("pageerror", (error) => errors.push(String(error)));
  await visitor.goto(BASE + "/", { waitUntil: "networkidle2" }).catch(() => {});
  check("sign-in offers to create an account", await waitText(visitor, "Нет аккаунта?"));
  check("sign-in offers to reset the password", await waitText(visitor, "Забыли пароль?", 5000));
  check("the field takes an e-mail or a username", await waitText(visitor, "E-mail или логин", 5000));
  await visitor.screenshot({ path: "/tmp/e2e/signup-signin.png" });

  // The sign-up form.
  await visitor.goto(BASE + "/register", { waitUntil: "networkidle2" }).catch(() => {});
  check("the sign-up form opens", await waitText(visitor, "Зарегистрироваться"));
  check("it asks for both consents", await waitText(visitor, "договор-оферту", 5000) && (await waitText(visitor, "политике конфиденциальности", 5000)));
  check("it promises the bonus after confirmation", await waitText(visitor, "После подтверждения e-mail", 5000));
  await sleep(1500);
  await visitor.screenshot({ path: "/tmp/e2e/signup-register.png", fullPage: true });

  await visitor.goto(BASE + "/forgot-password", { waitUntil: "networkidle2" }).catch(() => {});
  check("the password reset page opens", await waitText(visitor, "Восстановить пароль"));
  await visitor.screenshot({ path: "/tmp/e2e/signup-forgot.png" });

  await visitor.goto(BASE + "/legal/offer", { waitUntil: "networkidle2" }).catch(() => {});
  check("the offer is public", await waitText(visitor, "Договор-оферта"));
  await sleep(800);
  await visitor.screenshot({ path: "/tmp/e2e/signup-offer.png" });

  // A new user who has not confirmed the e-mail sees the banner.
  const newcomer = await fresh(browser);
  newcomer.on("pageerror", (error) => errors.push(String(error)));
  await newcomer.goto(BASE + "/api/v1/auth/status");
  const signed = await newcomer.evaluate(async () => {
    const r = await fetch("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Forwarded-For": "5.45.192.77" },
      body: JSON.stringify({ email: `ui-${Date.now()}@example.com`, password: "ui-pass-1234", accept_offer: true, accept_privacy: true, captcha: "good-token" }),
    });
    return r.status;
  });
  check("a browser user signs up", signed === 200, String(signed));
  await newcomer.goto(BASE + "/dashboard", { waitUntil: "networkidle2" }).catch(() => {});
  check("the dashboard asks to confirm the e-mail", await waitText(newcomer, "Подтвердите e-mail"));
  check("the welcome says the bonus comes after confirmation", await waitText(newcomer, "после подтверждения e-mail", 10000));
  await sleep(800);
  await newcomer.screenshot({ path: "/tmp/e2e/signup-dashboard.png" });

  // Admin → Sign-up and Documents.
  const admin = await fresh(browser);
  admin.on("pageerror", (error) => errors.push(String(error)));
  await admin.goto(BASE + "/api/v1/auth/status");
  await admin.evaluate(async (c) => fetch("/api/v1/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(c) }), ADMIN);
  await admin.goto(BASE + "/admin", { waitUntil: "networkidle2" }).catch(() => {});
  await waitText(admin, "Регистрация");
  for (const [tab, text, shot] of [["Регистрация", "Почта настроена", "signup-admin"], ["Документы", "Политика обработки персональных данных", "signup-admin-legal"]]) {
    for (const button of await admin.$$("button[role=tab]")) {
      if ((await button.evaluate((el) => el.textContent)).trim() === tab) await button.click();
    }
    check(`Admin → ${tab} opens`, await waitText(admin, text, 15000));
    await sleep(800);
    await admin.screenshot({ path: `/tmp/e2e/${shot}.png`, fullPage: true });
  }
  const users = await admin.evaluate(async () => (await fetch("/api/v1/admin/users")).json());
  check("the user list knows who is not confirmed", users.some((user) => user.verified === false), JSON.stringify(users).slice(0, 200));

  check("no page errors", errors.length === 0, errors.join(" | ").slice(0, 300));
  await browser.close();
  const failed = results.filter((r) => !r[1]);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
