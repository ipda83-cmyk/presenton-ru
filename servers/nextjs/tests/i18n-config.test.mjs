import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import { build } from "esbuild";

let config;
let temporaryDirectory;

test.before(async () => {
  temporaryDirectory = await mkdtemp(path.join(tmpdir(), "presenton-i18n-config-"));
  const outputFile = path.join(temporaryDirectory, "bundle.mjs");
  await build({
    entryPoints: [path.resolve("i18n/config.ts")],
    outfile: outputFile,
    bundle: true,
    platform: "node",
    format: "esm",
    logLevel: "silent",
  });
  config = await import(`${pathToFileURL(outputFile).href}?cache=${Date.now()}`);
});

test.after(async () => {
  if (temporaryDirectory) {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
});

// Same cases as test_negotiate_locale in servers/fastapi/tests/unit/test_i18n.py:
// the UI and the backend errors must pick the same language for "auto".
const NEGOTIATION_CASES = [
  ["en-US,en;q=0.9", "en"],
  ["ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7", "ru"],
  ["de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7", "en"],
  ["de,fr", null],
  ["en;q=0.5, ru;q=0.8", "ru"],
  ["ru;q=0, en", "en"],
  ["en;q=abc, ru", "ru"],
  ["*", null],
  ["  EN-gb ", "en"],
  ["", null],
  [null, null],
];

test("negotiateLocale picks the first supported browser language by q-value", () => {
  for (const [header, expected] of NEGOTIATION_CASES) {
    assert.equal(config.negotiateLocale(header), expected, String(header));
  }
});

test("normalizePreference accepts ru, en and auto", () => {
  assert.equal(config.normalizePreference("auto"), "auto");
  assert.equal(config.normalizePreference(" AUTO "), "auto");
  assert.equal(config.normalizePreference("en-US"), "en");
  assert.equal(config.normalizePreference("automatic"), null);
  assert.equal(config.normalizePreference(undefined), null);
});

test("resolveLocale follows the browser only for auto", () => {
  const englishBrowser = "en-US,en;q=0.9";
  assert.equal(config.resolveLocale("auto", englishBrowser), "en");
  assert.equal(config.resolveLocale("auto", "ru-RU,ru"), "ru");
  assert.equal(config.resolveLocale("auto", "de"), "ru");
  assert.equal(config.resolveLocale("auto", null), "ru");
  assert.equal(config.resolveLocale("ru", englishBrowser), "ru");
  assert.equal(config.resolveLocale(undefined, englishBrowser), "ru");
  assert.equal(config.resolveLocale("klingon", englishBrowser), "ru");
  assert.equal(config.resolveLocale("en", null), "en");
});
