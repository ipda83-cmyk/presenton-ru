// PNG copies for the SVG pictures of an exported PPTX.
//
// The export package (@presenton/export-core) writes vector pictures (icons,
// markers, lines, decorations) as SVG only: <a:blip> without r:embed plus the
// Office 2016 svgBlip extension. PowerPoint 2016/2019, LibreOffice, Keynote
// and Google Slides then show "the picture can't be displayed". The standard
// form is a PNG in <a:blip r:embed> with the SVG in the extension, which every
// program shows and PowerPoint 365 still draws as a vector.
//
//   node pptx-svg-fallback.mjs <file.pptx> <export package dir>
//
// Rewrites the file in place; prints {"pictures": n} as JSON.

import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { join } from "node:path";

const [, , pptxPath, packageDir] = process.argv;
if (!pptxPath || !packageDir) {
  console.error("usage: node pptx-svg-fallback.mjs <file.pptx> <export package dir>");
  process.exit(2);
}
// jszip and sharp come with the export package.
const require = createRequire(join(packageDir, "package.json"));
const JSZip = require("jszip");
const sharp = require("sharp");

const EMU_PER_PX = 9525;
const SCALE = 2; // pixels per CSS pixel: sharp on screens and projectors
const MAX_SIDE = 4096;
const BLIP_WITHOUT_EMBED =
  /<a:blip(?![^>]*\br:embed=)([^>]*)>(\s*<a:extLst>[\s\S]*?<asvg:svgBlip\b[^>]*\br:embed="([^"]+)"[\s\S]*?<\/a:extLst>\s*)<\/a:blip>/g;

function relationships(xml) {
  const map = new Map();
  for (const match of xml.matchAll(/<Relationship\b[^>]*>/g)) {
    const id = /\bId="([^"]+)"/.exec(match[0])?.[1];
    const target = /\bTarget="([^"]+)"/.exec(match[0])?.[1];
    if (id && target) map.set(id, target);
  }
  return map;
}

function resolve(slidePath, target) {
  const parts = slidePath.split("/").slice(0, -1);
  for (const piece of target.split("/")) {
    if (piece === "..") parts.pop();
    else if (piece && piece !== ".") parts.push(piece);
  }
  return parts.join("/");
}

function pictureSize(pictureXml) {
  const ext = /<a:xfrm\b[\s\S]*?<a:ext\b[^>]*\bcx="(\d+)"[^>]*\bcy="(\d+)"/.exec(pictureXml);
  if (!ext) return null;
  const side = (emu) => Math.min(MAX_SIDE, Math.max(2, Math.round((Number(emu) / EMU_PER_PX) * SCALE)));
  return { width: side(ext[1]), height: side(ext[2]) };
}

async function rasterize(svg, size) {
  const image = sharp(svg, { density: 300, limitInputPixels: false });
  const resized = size ? image.resize(size.width, size.height, { fit: "fill" }) : image;
  return resized.png({ compressionLevel: 9 }).toBuffer();
}

const zip = await JSZip.loadAsync(await readFile(pptxPath));
const parts = Object.keys(zip.files).filter((name) =>
  /^ppt\/(slides|slideLayouts|slideMasters)\/[^/]+\.xml$/.test(name),
);
const cache = new Map();
let pictures = 0;
let counter = 0;

for (const partPath of parts) {
  let xml = await zip.file(partPath).async("string");
  if (!xml.includes("svgBlip")) continue;
  const relsPath = partPath.replace(/([^/]+)$/, "_rels/$1.rels");
  const relsFile = zip.file(relsPath);
  if (!relsFile) continue;
  let rels = await relsFile.async("string");
  const targets = relationships(rels);
  let nextId = 1;
  while (targets.has(`rId${nextId}`)) nextId += 1;

  const replacements = [];
  for (const picture of xml.matchAll(/<p:pic>[\s\S]*?<\/p:pic>/g)) {
    const pictureXml = picture[0];
    BLIP_WITHOUT_EMBED.lastIndex = 0;
    const blip = BLIP_WITHOUT_EMBED.exec(pictureXml);
    if (!blip) continue;
    const svgTarget = targets.get(blip[3]);
    const svgFile = svgTarget ? zip.file(resolve(partPath, svgTarget)) : null;
    if (!svgFile) continue;
    const size = pictureSize(pictureXml);
    const key = `${svgTarget}|${size?.width}x${size?.height}`;
    let mediaName = cache.get(key);
    if (!mediaName) {
      try {
        const png = await rasterize(await svgFile.async("nodebuffer"), size);
        counter += 1;
        mediaName = `presenton-svg-fallback-${counter}.png`;
        zip.file(`ppt/media/${mediaName}`, png, { createFolders: false });
        cache.set(key, mediaName);
      } catch (error) {
        console.error(`could not draw ${svgTarget}: ${error.message}`);
        continue;
      }
    }
    const rId = `rId${nextId}`;
    nextId += 1;
    while (targets.has(`rId${nextId}`)) nextId += 1;
    targets.set(rId, `../media/${mediaName}`);
    rels = rels.replace(
      /<\/Relationships>\s*$/,
      `<Relationship Id="${rId}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/${mediaName}"/></Relationships>`,
    );
    const fixed = pictureXml.replace(blip[0], `<a:blip r:embed="${rId}"${blip[1]}>${blip[2]}</a:blip>`);
    replacements.push([pictureXml, fixed]);
    pictures += 1;
  }
  for (const [before, after] of replacements) xml = xml.replace(before, after);
  if (replacements.length) {
    zip.file(partPath, xml, { createFolders: false });
    zip.file(relsPath, rels, { createFolders: false });
  }
}

if (pictures) {
  const content = await zip.generateAsync({
    type: "nodebuffer",
    compression: "DEFLATE",
    compressionOptions: { level: 6 },
    mimeType: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  });
  await writeFile(pptxPath, content);
}
console.log(JSON.stringify({ pictures }));
