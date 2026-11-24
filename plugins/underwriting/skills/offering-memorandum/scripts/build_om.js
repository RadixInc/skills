#!/usr/bin/env node
/*
 * Build a full Offering Memorandum as an editable PowerPoint deck (and PDF) from om.json (radix.om/v2)
 * and a brand profile (radix.brand_profile/v1).
 *
 *   node build_om.js --om om.json --brand brand.json --out OUTDIR [--pdf] [--force]
 *
 * The OM is a recipe over the Radix data blocks: every financial and rent slide is drawn by
 * blocks_lib.js, the same code the deal-data-blocks skill uses, so the numbers look the same in a
 * Radix-built OM and in a broker's own document. This file adds only the OM's own pages: cover,
 * executive summary and offering terms, property overview and photos, section dividers, sales comps,
 * market overview, and contacts with the disclaimer.
 * Exit codes: 0 written, 2 accuracy gate failed (nothing written unless --force), 1 usage error.
 */
const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawnSync } = require("child_process");
let pptxgen;
try { pptxgen = require("pptxgenjs"); } catch (e) {
  console.error(JSON.stringify({ status: "error", error: "pptxgenjs is not installed. Run: npm install pptxgenjs" }));
  process.exit(1);
}
const createBlocks = require("./blocks_lib");

// ---------- args ----------
const args = process.argv.slice(2);
const arg = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const flag = (k) => args.includes(k);
const omPath = arg("--om"), outDir = arg("--out");
const brandPath = arg("--brand", path.join(__dirname, "..", "assets", "brand-radix-default.json"));
if (!omPath || !outDir) { console.error("usage: node build_om.js --om om.json --brand brand.json --out OUTDIR [--pdf] [--force]"); process.exit(1); }
const om = JSON.parse(fs.readFileSync(omPath, "utf8"));
const brand = JSON.parse(fs.readFileSync(brandPath, "utf8"));
if (om.schema !== "radix.om/v2") { console.error(JSON.stringify({ status: "error", error: "om.json must use schema radix.om/v2" })); process.exit(1); }

// The OM recipe: which blocks go in which section, in order. The property snapshot block is left out
// because the executive summary and property overview already carry those facts.
const RECIPE = [
  { section: "The property", blocks: ["unit_mix", "rents_vs_market"] },
  { section: "Financial analysis", blocks: ["operating_history", "operating_statement", "proforma_cash_flow", "proforma_assumptions"] },
  { section: "Market", blocks: ["rent_comps"] },
];
const sectionOf = {}; for (const r of RECIPE) for (const b of r.blocks) sectionOf[b] = r.section;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in

// Block slides in the OM get the OM's chrome: a title rule and a page number. Everything else about a block is unchanged.
const B = createBlocks({
  pres, data: om, brand,
  frame: { master: "OM_CONTENT", section: (id) => sectionOf[id], sourceWidth: 10.4, decorate: () => {} },
});
const { PRIMARY, ACCENT, TINT, INK, STRONG, MUTED, FAINT, RULE, CANVAS, FONT, W, X0, CW } = B.style;
const { isNum, money, compact, pct, int, dateLabel } = B.fmt;
const { deal, snap, units, um, act, rrDate } = B.facts;
const T = B.T, table = B.table;
const WARN = "B54708", WARN_BG = "FFFAEB";
const firm = (brand.firm || {}).display_name || (brand.logo || {}).wordmark_text || "";
pres.title = `${deal.name || "Property"} · Offering Memorandum`;
pres.company = firm;
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

// ---------- masters ----------
const titlePh = { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.4, w: CW, h: 0.6, fontFace: FONT, fontSize: 24, bold: true, color: STRONG, align: "left", valign: "top", margin: 0 }, text: "" } };
pres.defineSlideMaster({
  title: "OM_CONTENT",
  background: { color: "FFFFFF" },
  objects: [
    titlePh,
    { line: { x: X0, y: 1.33, w: CW, h: 0, line: { color: ACCENT, width: 1.25 } } },
    { text: { text: `${deal.name || ""}${firm ? `  ·  ${firm}` : ""}`, options: { x: W - X0 - 2.6, y: 6.85, w: 2.2, h: 0.3, fontFace: FONT, fontSize: 9, color: FAINT, align: "right", margin: 0 } } },
  ],
  slideNumber: { x: W - X0 - 0.35, y: 6.85, w: 0.35, h: 0.3, fontFace: FONT, fontSize: 9, color: FAINT, align: "right" },
});
pres.defineSlideMaster({ title: "OM_COVER", background: { color: PRIMARY }, objects: [] });
pres.defineSlideMaster({
  title: "OM_DIVIDER", background: { color: PRIMARY },
  objects: [{ line: { x: X0, y: 3.95, w: 1.2, h: 0, line: { color: "FFFFFF", width: 2 } } }],
  slideNumber: { x: W - X0 - 0.35, y: 6.85, w: 0.35, h: 0.3, fontFace: FONT, fontSize: 9, color: "FFFFFF", align: "right" },
});

const placeholders = [];
const content = (title, section, subject) => {
  const s = pres.addSlide({ masterName: "OM_CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title", align: "left" });
  if (subject) T(s, subject, { x: X0, y: 0.98, w: CW, h: 0.3, fontSize: 12, color: FAINT });
  return s;
};
const sections = new Set();
const section = (name) => { if (!sections.has(name)) { sections.add(name); pres.addSection({ title: name }); } return name; };
const divider = (name, n) => {
  const s = pres.addSlide({ masterName: "OM_DIVIDER", sectionTitle: section(name) });
  T(s, String(n).padStart(2, "0"), { x: X0, y: 2.6, w: 3, h: 0.9, fontSize: 40, bold: true, color: "DBE6FC" });
  T(s, name, { x: X0, y: 4.15, w: 10, h: 0.9, fontSize: 40, bold: true, color: "FFFFFF" });
};
function placeholderBox(s, x, y, w, h, title, body) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: WARN_BG }, line: { color: "FEDF89", width: 1, dashType: "dash" } });
  T(s, [{ text: title, options: { bold: true, color: WARN, fontSize: 16, align: "center", breakLine: true } }, { text: body, options: { color: MUTED, fontSize: 13, align: "center" } }],
    { x: x + 0.5, y: y + 0.25, w: w - 1.0, h: h - 0.5, valign: "middle", align: "center", paraSpaceAfter: 6 });
}
const source = (s, text) => T(s, text, { x: X0, y: 6.8, w: 10.4, h: 0.4, fontSize: 10, color: FAINT });

// ---------- plan and gate ----------
const wanted = om.blocks && om.blocks.length ? om.blocks : RECIPE.flatMap((r) => r.blocks);
let plan;
try { plan = B.plan(wanted.filter((b) => sectionOf[b])); } catch (e) { console.error(JSON.stringify({ status: "error", error: e.message })); process.exit(1); }
const { rendered, skipped } = plan;
const checks = B.gate(rendered);
const check = (name, ok, detail = "") => checks.push({ check: name, ok: !!ok, detail });

// ===== 1. Cover
const photos = om.photos || [];
{
  const s = pres.addSlide({ masterName: "OM_COVER", sectionTitle: section("Cover") });
  T(s, "OFFERING MEMORANDUM", { x: X0, y: 0.8, w: 6, h: 0.35, fontSize: 12, bold: true, color: "FFFFFF", charSpacing: 3 });
  T(s, deal.name || "", { x: X0, y: 2.1, w: 6.4, h: 1.5, fontSize: 44, bold: true, color: "FFFFFF", valign: "bottom" });
  T(s, deal.address || "", { x: X0, y: 3.7, w: 6.4, h: 0.4, fontSize: 16, color: "FFFFFF" });
  const facts = [isNum(units) ? `${int(units)} units` : null, deal.year_built ? `Built ${deal.year_built}` : null, deal.building_type || null].filter(Boolean).join("  ·  ");
  T(s, facts, { x: X0, y: 4.15, w: 6.4, h: 0.4, fontSize: 14, color: "DBE6FC" });
  if ((brand.logo || {}).data_uri) s.addImage({ data: brand.logo.data_uri, x: X0, y: 6.2, w: 2.2, h: 0.7, sizing: { type: "contain", w: 2.2, h: 0.7 }, altText: `${firm} logo` });
  else T(s, firm, { x: X0, y: 6.4, w: 5, h: 0.45, fontSize: 18, bold: true, color: "FFFFFF" });
  if (photos.length) {
    s.addImage({ path: photos[0].path, x: 7.4, y: 0, w: W - 7.4, h: 7.5, sizing: { type: "cover", w: W - 7.4, h: 7.5 }, altText: photos[0].caption || "Property photo" });
  } else {
    s.addShape(pres.shapes.RECTANGLE, { x: 7.4, y: 0, w: W - 7.4, h: 7.5, fill: { color: "FFFFFF", transparency: 88 }, line: { type: "none" } });
    T(s, "Property photo\nAdd the hero image here", { x: 7.4, y: 3.2, w: W - 7.4, h: 1.0, fontSize: 14, color: "DBE6FC", align: "center", valign: "middle" });
    placeholders.push("Cover photo.");
  }
}

// ===== 2. Executive summary: deal at a glance
{
  const s = content("Executive summary", section("Executive summary"), [deal.address, rrDate ? `Rent roll as of ${rrDate}` : null].filter(Boolean).join(" · "));
  T(s, om.summary || "", { x: X0, y: 1.55, w: 7.3, h: 1.2, fontSize: 14, color: INK, paraSpaceAfter: 6 });
  if (!om.summary) placeholders.push("Executive summary text.");
  let y = 2.9;
  (om.highlights || []).slice(0, 4).forEach((h, i) => {
    s.addShape(pres.shapes.OVAL, { x: X0, y: y + 0.02, w: 0.34, h: 0.34, fill: { color: PRIMARY }, line: { type: "none" } });
    T(s, String(i + 1), { x: X0, y: y + 0.02, w: 0.34, h: 0.34, fontSize: 11, bold: true, color: "FFFFFF", align: "center", valign: "middle" });
    T(s, [{ text: h.title, options: { bold: true, fontSize: 14, color: STRONG, breakLine: true } }, { text: h.text, options: { fontSize: 12, color: MUTED } }],
      { x: X0 + 0.5, y, w: 6.8, h: 0.85 });
    y += 0.92;
  });
  if (!(om.highlights || []).length) placeholders.push("Investment highlights.");
  // offering terms
  const ox = 8.4, ow = W - X0 - ox, off = om.offering || {};
  const terms = [["Price", isNum(off.price) ? money(off.price) : off.price_label || "Unpriced"], ["Price per unit", isNum(off.price) && units ? money(off.price / units) : null],
    ["Offers due", off.offers_due ? dateLabel(off.offers_due) : "To be announced"]].filter((r) => r[1]).concat((off.terms || []).map((t) => [t.label, t.value]));
  if (!isNum(off.price) && !off.price_label) placeholders.push("Offering price, or 'Unpriced'.");
  if (!off.offers_due) placeholders.push("Offer due date.");
  const ph = 0.75 + 0.36 * terms.length;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ox, y: 1.55, w: ow, h: ph, rectRadius: 0.08, fill: { color: TINT }, line: { color: RULE, width: 0.75 } });
  T(s, "Offering", { x: ox + 0.25, y: 1.7, w: ow - 0.5, h: 0.35, fontSize: 13, bold: true, color: STRONG });
  terms.forEach(([a, b], i) => {
    T(s, a, { x: ox + 0.25, y: 2.15 + i * 0.36, w: 1.6, h: 0.3, fontSize: 12, color: FAINT });
    T(s, String(b), { x: ox + 1.9, y: 2.15 + i * 0.36, w: ow - 2.15, h: 0.3, fontSize: 12, bold: true, color: INK, align: "right" });
  });
  const t12noi = (act.noi || {}).T12;
  const stats = [["Units", int(units)], ["Occupancy", pct(snap.occupancy_pct)], ["In-place as % of market", pct(snap.pct_of_market)], ["T12 NOI", compact(t12noi)]];
  const sy0 = 1.55 + ph + 0.25, th = Math.min(1.2, (6.6 - sy0 - 0.15) / 2);
  stats.forEach(([label, val], i) => {
    const sw = (ow - 0.15) / 2, sx = ox + (i % 2) * (sw + 0.15), sy = sy0 + Math.floor(i / 2) * (th + 0.15);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: sx, y: sy, w: sw, h: th, rectRadius: 0.08, fill: { color: "FFFFFF" }, line: { color: RULE, width: 0.75 } });
    T(s, label, { x: sx + 0.18, y: sy + 0.14, w: sw - 0.36, h: 0.3, fontSize: 11, color: MUTED });
    T(s, val, { x: sx + 0.18, y: sy + 0.45, w: sw - 0.36, h: th - 0.55, fontSize: 24, bold: true, color: PRIMARY });
  });
  source(s, `Facts from the Radix deal record, rent roll as of ${rrDate} and operating statement. Summary and highlights drafted from those figures; edit before sending.`);
  s.addNotes("The summary and highlights are drafted from Radix data. Edit them before sending.");
}

// ===== 3. Property section
divider("The property", 1);
{
  const s = content("Property overview", section("The property"), deal.address);
  const rows = [["Address", deal.address], ["Market", deal.market], ["Year built", deal.year_built ? String(deal.year_built) : null], ["Building type", deal.building_type],
    ["Units", isNum(units) ? int(units) : null], ["Rentable SF", isNum(deal.total_sf) ? int(deal.total_sf) : null], ["Average unit size", isNum((um.total || {}).avg_sf) ? `${int(um.total.avg_sf)} SF` : null],
    ["Occupancy", isNum(snap.occupancy_pct) ? `${pct(snap.occupancy_pct)} on the ${rrDate} rent roll` : null]].concat((om.property_facts || []).map((f) => [f.label, f.value])).filter((r) => r[1]);
  let y = 1.6;
  const rh = Math.min(0.52, 4.9 / Math.max(rows.length, 1));
  for (const [a, b] of rows) {
    T(s, a, { x: X0, y, w: 2.1, h: 0.4, fontSize: 13, color: FAINT });
    T(s, String(b), { x: X0 + 2.2, y, w: 4.3, h: 0.4, fontSize: 13, bold: true, color: INK });
    s.addShape(pres.shapes.LINE, { x: X0, y: y + rh - 0.08, w: 6.5, h: 0, line: { color: RULE, width: 0.75 } });
    y += rh;
  }
  const am = om.amenities || {};
  const amenText = [["Community", am.community], ["Unit", am.unit]].filter(([, v]) => (v || []).length);
  if (amenText.length) {
    let ay = 1.6;
    const ax = 7.5, aw = W - X0 - ax;
    const mapH = om.map && om.map.path ? 2.6 : 0;
    if (mapH) s.addImage({ path: om.map.path, x: ax, y: ay, w: aw, h: mapH, sizing: { type: "contain", w: aw, h: mapH }, altText: "Location map" });
    ay += mapH ? mapH + 0.2 : 0;
    for (const [h, list] of amenText) {
      T(s, h + " amenities", { x: ax, y: ay, w: aw, h: 0.35, fontSize: 13, bold: true, color: STRONG });
      T(s, list.map((t) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: true } })), { x: ax, y: ay + 0.4, w: aw, h: 0.28 * list.length, fontSize: 11, color: MUTED });
      ay += 0.5 + 0.28 * list.length;
    }
    if (!mapH) {
      if (6.5 - ay > 1.4) placeholderBox(s, ax, ay, aw, 6.5 - ay, "Location map", "Add a site or location map.");
      placeholders.push("Location map.");
    }
  } else if (om.map && om.map.path) {
    s.addImage({ path: om.map.path, x: 7.5, y: 1.6, w: W - X0 - 7.5, h: 4.9, sizing: { type: "contain", w: W - X0 - 7.5, h: 4.9 }, altText: "Location map" });
  } else {
    placeholderBox(s, 7.5, 1.6, W - X0 - 7.5, 4.9, "Location map", "Add a site or location map. Maps aren't generated yet.");
    placeholders.push("Location map.");
  }
  source(s, "Radix deal record and rent roll. Amenities and map supplied by the broker.");
}
// Photo page: up to 4 photos after the cover photo.
{
  const more = photos.slice(1, 5);
  const s = content("Property photos", section("The property"));
  if (more.length) {
    const g = 0.2, cols = more.length === 1 ? 1 : 2, rowsN = Math.ceil(more.length / cols);
    const pw = (CW - g * (cols - 1)) / cols, ph = (5.2 - g * (rowsN - 1)) / rowsN;
    more.forEach((p, i) => s.addImage({ path: p.path, x: X0 + (i % cols) * (pw + g), y: 1.55 + Math.floor(i / cols) * (ph + g), w: pw, h: ph, sizing: { type: "cover", w: pw, h: ph }, altText: p.caption || "Property photo" }));
  } else {
    placeholderBox(s, X0, 1.55, CW, 5.0, "Property photos", "Add exterior, amenity and unit interior photos here.");
    placeholders.push("Property photos.");
  }
}
const drawSection = (name) => { for (const b of rendered) if (sectionOf[b] === name) B.draw[b](); };
drawSection("The property");

// ===== 4. Financial analysis
divider("Financial analysis", 2);
drawSection("Financial analysis");

// ===== 5. Market
divider("Market", 3);
drawSection("Market");
{
  const sc = om.sales_comps || {};
  const s = content("Sales comparables", section("Market"), sc.rows && sc.rows.length ? `${sc.rows.length} sales` : null);
  if ((sc.rows || []).length) {
    const rows = sc.rows.map((r) => ({ cells: [`${r.name}${r.city ? `, ${r.city}` : ""}`, r.sale_date ? dateLabel(r.sale_date) : "-", int(r.units), r.year_built ? String(r.year_built) : "-",
      money(r.price), isNum(r.price_per_unit) ? money(r.price_per_unit) : (isNum(r.price) && r.units ? money(r.price / r.units) : "-"), isNum(r.cap_rate) ? pct(r.cap_rate, 2) : "-"] }));
    table(s, ["Property", "Sale date", "Units", "Year built", "Price", "Price per unit", "Cap rate"], rows, { x: X0, y: 1.55, w: CW, colW: B.evenCols(CW, 3.6, 6), fontSize: 11, rowH: Math.min(0.42, 5.0 / (rows.length + 1)) });
    source(s, sc.source || "Sales comparables as supplied.");
    check("Every sales comp has a sale date and price", sc.rows.every((r) => r.sale_date && isNum(r.price)));
    check("Sales comps name their source", !!sc.source);
  } else {
    placeholderBox(s, X0, 1.55, CW, 5.0, "Sales comparables", "Radix doesn't hold sales comps yet. Add recent sales (price, price per unit, cap rate), or ask Claude to research them.");
    placeholders.push("Sales comparables.");
  }
}
{
  const mo = om.market_overview || {};
  const s = content("Market overview", section("Market"), deal.market);
  if ((mo.points || []).length) {
    T(s, mo.points.slice(0, 8).map((p) => ({ text: p.text, options: { bullet: { indent: 16 }, breakLine: true, paraSpaceAfter: 8 } })), { x: X0, y: 1.6, w: CW, h: 5.0, fontSize: 14, color: INK });
    source(s, `Sources: ${[...new Set(mo.points.map((p) => p.source))].join("; ")}`);
    check("Every market point names its source", mo.points.every((p) => p.source));
  } else {
    placeholderBox(s, X0, 1.55, CW, 5.0, "Market overview", "Add the submarket story: population and job growth, major employers, new supply. Claude can research it with sources.");
    placeholders.push("Market overview.");
  }
}

// ===== 6. Contacts and disclaimer
{
  const s = content("Contacts", section("Contacts"), firm);
  const lines = (brand.firm || {}).contact_lines || [];
  if (lines.length) T(s, lines.map((l) => ({ text: l, options: { breakLine: true, paraSpaceAfter: 10 } })), { x: X0, y: 1.6, w: 7, h: 3.4, fontSize: 15, color: INK });
  else { placeholderBox(s, X0, 1.6, 7, 3.0, "Broker team", "Add names, titles, phone and email (firm.contact_lines in brand.json)."); placeholders.push("Broker contacts."); }
  T(s, brand.om_disclaimer || "", { x: X0, y: 5.1, w: CW, h: 1.5, fontSize: 9, color: FAINT });
}

// ---------- drafted text may only cite figures the deck prints ----------
const tokens = (t) => (String(t || "").match(/\$?\d[\d,]*(?:\.\d+)?\s?(?:%|[MK]\b)?/g) || []).map((x) => x.replace(/\s/g, "").replace(/[,.]+$/, ""))
  .filter((x) => /[$%MK.,]/.test(x) || x.replace(/\D/g, "").length >= 3);
const drafted = [om.summary].concat((om.highlights || []).flatMap((h) => [h.title, h.text]));
const draftedSet = new Set(drafted.filter(Boolean).map(String));
const printed = B.shown.filter((x) => !draftedSet.has(x)).join(" | ");
const unprinted = [...new Set(drafted.flatMap(tokens))].filter((tk) => !printed.includes(tk));
check("Summary and highlights only cite figures the deck prints", !unprinted.length, unprinted.join(", "));
check("At most 4 highlights", (om.highlights || []).length <= 4);

// ---------- write ----------
const failed = checks.filter((c) => !c.ok);
const status = failed.length ? "fail" : "pass";
if (failed.length && !flag("--force")) { console.log(JSON.stringify({ status, failed }, null, 2)); process.exit(2); }
fs.mkdirSync(outDir, { recursive: true });
const stem = (deal.name || "Property").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "") + "-OM";
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
  let pdfNote = null;
  if (flag("--pdf")) {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "om-"));
    spawnSync("soffice", ["--headless", "--convert-to", "pdf", "--outdir", tmp, pptxPath], { timeout: 240000 });
    const pdf = path.join(tmp, `${stem}.pdf`);
    if (fs.existsSync(pdf)) { const dst = path.join(outDir, `${stem}.pdf`); fs.copyFileSync(pdf, dst); outputs.push(dst); }
    else pdfNote = "PDF not written: LibreOffice (soffice) not available. Save the .pptx as PDF from PowerPoint.";
  }
  const summary = [`# Run summary: ${deal.name} Offering Memorandum`, "", `Accuracy gate: **${status}**`, "",
    "## Radix blocks in the OM"].concat(rendered.map((b) => `- ${b}`),
    skipped.length ? ["", "## Blocks left out (missing data)"].concat(skipped.map((s) => `- ${s.block}: needs ${s.needs}`)) : [],
    placeholders.length ? ["", "## Placeholders to fill"].concat(placeholders.map((p) => `- ${p}`)) : [],
    B.colorNotes.length ? ["", "## Brand colors"].concat(B.colorNotes.map((n) => `- ${n}`)) : [],
    ["", "## Checks"], checks.map((c) => `- ${c.ok ? "PASS" : "FAIL"}: ${c.check}${!c.ok && c.detail ? ` (${c.detail})` : ""}`),
    ["", "## Files"], outputs.map((o) => `- ${o}`), pdfNote ? [`- ${pdfNote}`] : []).join("\n");
  fs.writeFileSync(path.join(outDir, `${stem}-run-summary.md`), summary + "\n");
  console.log(JSON.stringify({ status, blocks: rendered, skipped, placeholders, outputs, pdf_note: pdfNote, color_notes: B.colorNotes, failed }, null, 2));
});
