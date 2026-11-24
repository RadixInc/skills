#!/usr/bin/env node
/*
 * Render Radix data blocks for a deal: one block per slide in an editable PowerPoint file,
 * and optionally one PNG per block, from blocks.json (radix.deal_blocks/v1) and a brand profile.
 *
 *   node build_blocks.js --data blocks.json --brand brand.json --out OUTDIR [--png] [--force]
 *
 * Every block has a fixed frame (title, subject line, content, source line) and a fixed design,
 * so a block looks the same in every deal and every document it is pasted into.
 * The agent only gathers data and picks blocks; it never writes text that lands on a block.
 * Exit codes: 0 written, 2 accuracy gate failed (nothing written unless --force), 1 usage error.
 */
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
let pptxgen;
try { pptxgen = require("pptxgenjs"); } catch (e) {
  console.error(JSON.stringify({ status: "error", error: "pptxgenjs is not installed. Run: npm install pptxgenjs" }));
  process.exit(1);
}

// ---------- args ----------
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const flag = (k) => args.includes(k);
const dataPath = arg("--data"), outDir = arg("--out");
const brandPath = arg("--brand", path.join(__dirname, "..", "assets", "brand-radix-default.json"));
if (!dataPath || !outDir) { console.error("usage: node build_blocks.js --data blocks.json --brand brand.json --out OUTDIR [--png] [--force]"); process.exit(1); }
const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const brand = JSON.parse(fs.readFileSync(brandPath, "utf8"));
if (data.schema !== "radix.deal_blocks/v1") { console.error(JSON.stringify({ status: "error", error: "blocks.json must use schema radix.deal_blocks/v1" })); process.exit(1); }
const createBlocks = require("./blocks_lib");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
const B = createBlocks({ pres, data, brand });
const { FONT } = B.style;
const deal = data.deal || {};
pres.title = `${deal.name || "Property"} · Radix data blocks`;
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

let plan;
try { plan = B.plan(data.blocks); } catch (e) { console.error(JSON.stringify({ status: "error", error: e.message, catalog: B.CATALOG })); process.exit(1); }
const { rendered, skipped } = plan;
const checks = B.gate(rendered), colorNotes = B.colorNotes;
for (const b of rendered) B.draw[b]();
// ---------- write ----------
const failed = checks.filter((c) => !c.ok);
const status = failed.length ? "fail" : skipped.length ? "pass_with_skipped_blocks" : "pass";
if (failed.length && !flag("--force")) { console.log(JSON.stringify({ status, failed }, null, 2)); process.exit(2); }
if (!rendered.length) { console.log(JSON.stringify({ status: "nothing_to_render", skipped }, null, 2)); process.exit(2); }
fs.mkdirSync(outDir, { recursive: true });
const stem = (deal.name || "Property").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "") + "-Radix-blocks";
const pptxPath = path.join(outDir, `${stem}.pptx`);
pres.writeFile({ fileName: pptxPath }).then(async () => {
  // pptxgenjs writes folder entries into the ZIP; cloud editors refuse those. Repack without them.
  try {
    const JSZip = require(require.resolve("jszip", { paths: [path.dirname(require.resolve("pptxgenjs"))] }));
    const zin = await JSZip.loadAsync(fs.readFileSync(pptxPath));
    const zout = new JSZip();
    const names = Object.keys(zin.files).filter((k) => !zin.files[k].dir);
    names.sort((a, b) => (a === "[Content_Types].xml" ? -1 : b === "[Content_Types].xml" ? 1 : 0));
    for (const k of names) zout.file(k, await zin.files[k].async("nodebuffer"), { createFolders: false });
    const buf = await zout.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
    if (names.length > 10) fs.writeFileSync(pptxPath, buf);
  } catch (e) { /* leave the file as written */ }
  const outputs = [pptxPath];
  let pngNote = null;
  if (flag("--png")) {
    // One PNG per block, named by its position and block id.
    const tmp = fs.mkdtempSync(path.join(require("os").tmpdir(), "blocks-"));
    spawnSync("soffice", ["--headless", "--convert-to", "pdf", "--outdir", tmp, pptxPath], { timeout: 180000 });
    const pdf = path.join(tmp, `${stem}.pdf`);
    if (fs.existsSync(pdf)) {
      const pngDir = path.join(outDir, `${stem}-png`);
      fs.mkdirSync(pngDir, { recursive: true });
      const r = spawnSync("pdftoppm", ["-png", "-r", "150", pdf, path.join(tmp, "p")]);
      const pages = fs.readdirSync(tmp).filter((f) => /^p-\d+\.png$/.test(f)).sort();
      if (r.status === 0 && pages.length === rendered.length) {
        pages.forEach((f, i) => { const dst = path.join(pngDir, `${String(i + 1).padStart(2, "0")}-${rendered[i].replace(/_/g, "-")}.png`); fs.copyFileSync(path.join(tmp, f), dst); outputs.push(dst); });
      } else pngNote = "PNGs not written: pdftoppm (poppler) not available.";
    } else pngNote = "PNGs not written: LibreOffice (soffice) not available. Open the .pptx and export the slides as pictures.";
  }
  const summary = [`# Run summary: ${deal.name} Radix data blocks`, "", `Accuracy gate: **${status.replace(/_/g, " ")}**`, "", "## Blocks"]
    .concat(rendered.map((b, i) => `${i + 1}. ${b}`), skipped.length ? ["", "## Skipped (missing data)"].concat(skipped.map((s) => `- ${s.block}: needs ${s.needs}`)) : [],
      colorNotes.length ? ["", "## Brand colors"].concat(colorNotes.map((n) => `- ${n}`)) : [],
      ["", "## Checks"], checks.map((c) => `- ${c.ok ? "PASS" : "FAIL"}: ${c.check}${!c.ok && c.detail ? ` (${c.detail})` : ""}`),
      ["", "## Files"], outputs.map((o) => `- ${o}`), pngNote ? [`- ${pngNote}`] : []).join("\n");
  fs.writeFileSync(path.join(outDir, `${stem}-run-summary.md`), summary + "\n");
  console.log(JSON.stringify({ status, rendered, skipped, outputs, png_note: pngNote, color_notes: colorNotes, failed }, null, 2));
});
