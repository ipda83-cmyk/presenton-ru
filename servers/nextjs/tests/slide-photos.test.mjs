import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import { build } from "esbuild";

let photos;
let temporaryDirectory;

test.before(async () => {
  temporaryDirectory = await mkdtemp(path.join(tmpdir(), "presenton-slide-photos-"));
  const entryFile = path.join(temporaryDirectory, "entry.ts");
  const outputFile = path.join(temporaryDirectory, "bundle.mjs");
  await writeFile(
    entryFile,
    `export { remapSlidePhotos, normalizeSlidePhotosRecord, isSlidePhotoFile } from ${JSON.stringify(
      path.resolve("app/(presentation-generator)/services/api/slide-photos.ts"),
    )};`,
  );
  await build({
    entryPoints: [entryFile],
    outfile: outputFile,
    bundle: true,
    platform: "node",
    format: "esm",
    tsconfig: path.resolve("tsconfig.json"),
    logLevel: "silent",
  });
  photos = await import(`${pathToFileURL(outputFile).href}?cache=${Date.now()}`);
});

test.after(async () => {
  if (temporaryDirectory) {
    await rm(temporaryDirectory, { recursive: true, force: true });
  }
});

const photo = (url, slide) => ({ url, name: url, slide });

test("photos follow their slides when the outline is reordered", () => {
  // Slide 0 dragged to the end: [1, 2, 0] lists the old index now at each place.
  const moved = photos.remapSlidePhotos([photo("a", 0), photo("b", 2), photo("c", null)], [1, 2, 0]);
  assert.deepEqual(
    moved.map((item) => item.slide),
    [2, 1, null],
  );
});

test("a photo whose slide is gone is no longer used", () => {
  const moved = photos.remapSlidePhotos([photo("a", 3)], [0, 1, null]);
  assert.equal(moved[0].slide, null);
});

test("records from the server are cleaned up", () => {
  const record = photos.normalizeSlidePhotosRecord({
    photos: [
      { url: "/app_data/images/a.png", name: "a.png", slide: 1 },
      { url: "", slide: 0 },
      { url: "/app_data/images/b.png", slide: -1 },
      { url: "/app_data/images/c.png", slide: 1.5 },
      "junk",
    ],
    matched: "telepathy",
  });
  assert.deepEqual(record.photos, [
    { url: "/app_data/images/a.png", name: "a.png", slide: 1 },
    { url: "/app_data/images/b.png", name: "", slide: null },
    { url: "/app_data/images/c.png", name: "", slide: null },
  ]);
  assert.equal(record.matched, null);
  assert.deepEqual(photos.normalizeSlidePhotosRecord(null).photos, []);
});

test("only pictures count as slide photos", () => {
  const file = (name, type) => ({ name, type });
  assert.equal(photos.isSlidePhotoFile(file("sea.jpg", "image/jpeg")), true);
  assert.equal(photos.isSlidePhotoFile(file("logo.webp", "")), true);
  assert.equal(photos.isSlidePhotoFile(file("report.pdf", "application/pdf")), false);
  assert.equal(photos.isSlidePhotoFile(file("scan.tiff", "image/tiff")), false);
});
