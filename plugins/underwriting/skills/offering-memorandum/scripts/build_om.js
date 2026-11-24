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
// because the cover, executive summary and property overview already carry those facts.
const RECIPE = [
  { section: "The property", blocks: ["unit_mix", "rents_vs_market"] },
  { section: "Financial analysis", blocks: ["operating_history", "operating_statement", "proforma_cash_flow", "proforma_assumptions"] },
  { section: "Market", blocks: ["rent_comps"] },
];
const sectionOf = {}; for (const r of RECIPE) for (const b of r.blocks) sectionOf[b] = r.section;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in

// Block slides in the OM get the OM's running footer and page number. Everything else about a block is unchanged.
const B = createBlocks({ pres, data: om, brand, frame: { master: "OM_CONTENT", section: (id) => sectionOf[id] } });
const { PRIMARY, ACCENT, INK, MUTED, FAINT, HUSH, RULE, CANVAS, PAGE, FONT, DISPLAY, W, X0, CW } = B.style;
const { isNum, money, compact, pct, int, dateLabel } = B.fmt;
const { deal, snap, units, um, act, rrDate } = B.facts;
const T = B.T, table = B.table, card = B.card;
const WARN = "B54708";
const firm = (brand.firm || {}).display_name || (brand.logo || {}).wordmark_text || "";
pres.title = `${deal.name || "Property"} · Offering Memorandum`;
pres.company = firm;
pres.theme = { headFontFace: DISPLAY, bodyFontFace: FONT };

// ---------- masters ----------
const titlePh = { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.68, w: CW, h: 0.7, fontFace: DISPLAY, fontSize: 30, bold: false, color: INK, align: "left", valign: "top", margin: 0 }, text: "" } };
const running = `${(deal.name || "").toUpperCase()}  ·  OFFERING MEMORANDUM`;
pres.defineSlideMaster({
  title: "OM_CONTENT",
  background: { color: PAGE },
  objects: [
    titlePh,
    { line: { x: X0, y: 7.08, w: CW, h: 0, line: { color: RULE, width: 0.5 } } },
    { text: { text: running, options: { x: X0, y: 7.12, w: 8, h: 0.25, fontFace: FONT, fontSize: 7.5, bold: true, charSpacing: 1.5, color: FAINT, margin: 0 } } },
  ],
  slideNumber: { x: W - X0 - 0.6, y: 7.12, w: 0.6, h: 0.25, fontFace: FONT, fontSize: 8, color: FAINT, align: "right" },
});
pres.defineSlideMaster({ title: "OM_COVER", background: { color: PAGE }, objects: [] });
pres.defineSlideMaster({
  title: "OM_DIVIDER", background: { color: PAGE },
  objects: [{ text: { text: running, options: { x: X0, y: 7.12, w: 8, h: 0.25, fontFace: FONT, fontSize: 7.5, bold: true, charSpacing: 1.5, color: FAINT, margin: 0 } } }],
  slideNumber: { x: W - X0 - 0.6, y: 7.12, w: 0.6, h: 0.25, fontFace: FONT, fontSize: 8, color: FAINT, align: "right" },
});

const placeholders = [];
const eyebrow = (s, text, x, y, w, color) => T(s, String(text).toUpperCase(), { x, y, w, h: 0.25, fontSize: 9, bold: true, charSpacing: 1.5, color: color || FAINT });
const content = (title, section, subject) => {
  const s = pres.addSlide({ masterName: "OM_CONTENT", sectionTitle: section });
  s.addText(title, { placeholder: "title", align: "left" });
  eyebrow(s, [deal.name, subject].filter(Boolean).join(" · "), X0, 0.38, CW);
  return s;
};
const sections = new Set();
const section = (name) => { if (!sections.has(name)) { sections.add(name); pres.addSection({ title: name }); } return name; };
// Section break: a large numeral in the brand color, the section name, and what's inside it.
const divider = (name, n, inside) => {
  const s = pres.addSlide({ masterName: "OM_DIVIDER", sectionTitle: section(name) });
  T(s, String(n).padStart(2, "0"), { x: X0, y: 1.2, w: 4, h: 1.9, fontSize: 110, fontFace: DISPLAY, color: PRIMARY, valign: "bottom" });
  T(s, name, { x: X0, y: 3.35, w: 6.4, h: 1.0, fontSize: 48, fontFace: DISPLAY, color: INK });
  const lx = 7.9, lw = W - X0 - lx;
  eyebrow(s, "In this section", lx, 1.75, lw);
  inside.forEach((t, i) => {
    const y = 2.15 + i * 0.55;
    s.addShape(pres.shapes.LINE, { x: lx, y, w: lw, h: 0, line: { color: RULE, width: 0.5 } });
    T(s, String(i + 1).padStart(2, "0"), { x: lx, y: y + 0.13, w: 0.5, h: 0.3, fontSize: 10, color: FAINT });
    T(s, t, { x: lx + 0.55, y: y + 0.1, w: lw - 0.55, h: 0.35, fontSize: 14, color: INK });
  });
};
// Missing broker input: a quiet dashed card with a "To add" label, so it is plain what still needs filling.
function placeholderBox(s, x, y, w, h, title, body) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: CANVAS }, line: { color: HUSH, width: 0.75, dashType: "dash" } });
  eyebrow(s, "To add", x + 0.35, y + h / 2 - 0.75, w - 0.7, WARN);
  T(s, title, { x: x + 0.35, y: y + h / 2 - 0.45, w: w - 0.7, h: 0.5, fontSize: 20, fontFace: DISPLAY, color: INK });
  T(s, body, { x: x + 0.35, y: y + h / 2 + 0.1, w: Math.min(w - 0.7, 6), h: 0.7, fontSize: 11, color: MUTED });
}
const source = (s, text) => T(s, text, { x: X0, y: 6.78, w: CW, h: 0.3, fontSize: 8.5, color: FAINT });
const hair = (s, x, y, w) => s.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color: RULE, width: 0.5 } });

// ---------- plan and gate ----------
const wanted = om.blocks && om.blocks.length ? om.blocks : RECIPE.flatMap((r) => r.blocks);
let plan;
try { plan = B.plan(wanted.filter((b) => sectionOf[b])); } catch (e) { console.error(JSON.stringify({ status: "error", error: e.message })); process.exit(1); }
const { rendered, skipped } = plan;
const checks = B.gate(rendered);
const check = (name, ok, detail = "") => checks.push({ check: name, ok: !!ok, detail });
const titleOf = (b) => (b === "operating_statement" && B.facts.pf ? "Actuals to pro forma" : createBlocks.BLOCK_TITLES[b]);
const blocksIn = (name) => rendered.filter((b) => sectionOf[b] === name).map(titleOf);
const t12noi = (act.noi || {}).T12;

// ===== 1. Cover
const photos = om.photos || [];
{
  const s = pres.addSlide({ masterName: "OM_COVER", sectionTitle: section("Cover") });
  if ((brand.logo || {}).data_uri) s.addImage({ data: brand.logo.data_uri, x: X0, y: 0.5, w: 1.8, h: 0.5, sizing: { type: "contain", w: 1.8, h: 0.5 }, altText: `${firm} logo` });
  else T(s, firm, { x: X0, y: 0.55, w: 5, h: 0.4, fontSize: 15, bold: true, color: INK });
  eyebrow(s, "Offering memorandum", X0, 1.95, 6.2, PRIMARY);
  T(s, deal.name || "", { x: X0, y: 2.3, w: 6.4, h: 1.9, fontSize: 54, fontFace: DISPLAY, color: INK, valign: "top", lineSpacingMultiple: 0.95 });
  T(s, [deal.address, deal.market].filter(Boolean).join("  ·  "), { x: X0, y: 4.2, w: 6.4, h: 0.4, fontSize: 14, color: MUTED });
  // Stat strip
  const stats = [["Units", int(units)], ["Built", deal.year_built ? String(deal.year_built) : "-"], ["Occupancy", pct(snap.occupancy_pct)], ["T12 NOI", compact(t12noi)]];
  const sw = 6.4 / stats.length;
  hair(s, X0, 5.55, 6.4);
  stats.forEach(([label, val], i) => {
    const x = X0 + i * sw;
    if (i) s.addShape(pres.shapes.LINE, { x: x - 0.12, y: 5.75, w: 0, h: 0.95, line: { color: RULE, width: 0.5 } });
    T(s, val, { x, y: 5.7, w: sw - 0.2, h: 0.55, fontSize: 24, fontFace: DISPLAY, color: INK });
    eyebrow(s, label, x, 6.3, sw - 0.2);
  });
  const px = 7.45, py = 0.45, pw = W - 0.45 - px, ph = 7.5 - 0.9;
  if (photos.length) {
    s.addImage({ path: photos[0].path, x: px, y: py, w: pw, h: ph, sizing: { type: "cover", w: pw, h: ph }, altText: photos[0].caption || "Property photo" });
  } else {
    placeholderBox(s, px, py, pw, ph, "Cover photo", "Add the hero image of the property.");
    placeholders.push("Cover photo.");
  }
}

// ===== 2. Executive summary
{
  const s = content("Executive summary", section("Executive summary"), rrDate ? `Rent roll as of ${rrDate}` : null);
  const lw = 7.1;
  T(s, om.summary || "", { x: X0, y: 1.6, w: lw, h: 1.35, fontSize: 17, fontFace: DISPLAY, color: INK, lineSpacingMultiple: 1.1 });
  if (!om.summary) placeholders.push("Executive summary text.");
  const hl = (om.highlights || []).slice(0, 4);
  eyebrow(s, "Investment highlights", X0, 3.1, lw);
  const rh = Math.min(0.85, 3.25 / Math.max(hl.length, 1));
  hl.forEach((h, i) => {
    const y = 3.42 + i * rh;
    hair(s, X0, y, lw);
    T(s, String(i + 1).padStart(2, "0"), { x: X0, y: y + 0.1, w: 0.6, h: 0.4, fontSize: 18, fontFace: DISPLAY, color: PRIMARY });
    T(s, [{ text: h.title, options: { bold: true, fontSize: 12.5, color: INK, breakLine: true } }, { text: h.text, options: { fontSize: 11, color: MUTED } }],
      { x: X0 + 0.75, y: y + 0.1, w: lw - 0.75, h: rh - 0.12 });
  });
  if (!hl.length) placeholders.push("Investment highlights.");
  // Offering terms card
  const ox = 8.15, ow = W - X0 - ox, off = om.offering || {};
  const terms = [["Price", isNum(off.price) ? money(off.price) : off.price_label || "Unpriced"], ["Price per unit", isNum(off.price) && units ? money(off.price / units) : null],
    ["Offers due", off.offers_due ? dateLabel(off.offers_due) : "To be announced"]].filter((r) => r[1]).concat((off.terms || []).map((t) => [t.label, t.value]));
  if (!isNum(off.price) && !off.price_label) placeholders.push("Offering price, or 'Unpriced'.");
  if (!off.offers_due) placeholders.push("Offer due date.");
  const ch = 0.65 + 0.42 * terms.length;
  card(s, ox, 1.6, ow, ch);
  eyebrow(s, "Offering", ox + 0.3, 1.82, ow - 0.6, PRIMARY);
  terms.forEach(([a, b], i) => {
    const y = 2.17 + i * 0.42;
    if (i) hair(s, ox + 0.3, y - 0.04, ow - 0.6);
    T(s, a, { x: ox + 0.3, y: y + 0.04, w: 1.7, h: 0.3, fontSize: 11, color: MUTED });
    T(s, String(b), { x: ox + 2.0, y: y + 0.04, w: ow - 2.3, h: 0.3, fontSize: 11.5, bold: true, color: INK, align: "right" });
  });
  // Key figures
  const stats = [["Units", int(units)], ["Occupancy", pct(snap.occupancy_pct)], ["In-place as % of market", pct(snap.pct_of_market)], ["T12 NOI", compact(t12noi)]];
  const sy0 = 1.6 + ch + 0.2, gap = 0.2, sw = (ow - gap) / 2, th = Math.min(1.45, (6.6 - sy0 - gap) / 2);
  stats.forEach(([label, val], i) => {
    const sx = ox + (i % 2) * (sw + gap), sy = sy0 + Math.floor(i / 2) * (th + gap);
    card(s, sx, sy, sw, th);
    T(s, val, { x: sx + 0.25, y: sy + 0.15, w: sw - 0.5, h: th - 0.6, fontSize: 28, fontFace: DISPLAY, color: INK, valign: "bottom" });
    T(s, label, { x: sx + 0.25, y: sy + th - 0.42, w: sw - 0.5, h: 0.3, fontSize: 10, color: MUTED });
  });
  source(s, `Facts from the Radix deal record, rent roll as of ${rrDate} and operating statement. Summary and highlights drafted from those figures; edit before sending.`);
  s.addNotes("The summary and highlights are drafted from Radix data. Edit them before sending.");
}

// ===== 3. The property
divider("The property", 1, ["Property overview", "Property photos"].concat(blocksIn("The property")));
{
  const s = content("Property overview", section("The property"), deal.address);
  const rows = [["Address", deal.address], ["Market", deal.market], ["Year built", deal.year_built ? String(deal.year_built) : null], ["Building type", deal.building_type],
    ["Units", isNum(units) ? int(units) : null], ["Rentable SF", isNum(deal.total_sf) ? int(deal.total_sf) : null], ["Average unit size", isNum((um.total || {}).avg_sf) ? `${int(um.total.avg_sf)} SF` : null],
    ["Occupancy", isNum(snap.occupancy_pct) ? `${pct(snap.occupancy_pct)} on the ${rrDate} rent roll` : null]].concat((om.property_facts || []).map((f) => [f.label, f.value])).filter((r) => r[1]);
  const lw = 6.6, rh = Math.min(0.55, 4.95 / Math.max(rows.length, 1));
  rows.forEach(([a, b], i) => {
    const y = 1.6 + i * rh;
    hair(s, X0, y, lw);
    T(s, a, { x: X0, y: y + 0.13, w: 2.1, h: 0.3, fontSize: 11, color: MUTED });
    T(s, String(b), { x: X0 + 2.2, y: y + 0.11, w: lw - 2.2, h: 0.35, fontSize: 13, color: INK });
  });
  hair(s, X0, 1.6 + rows.length * rh, lw);
  const ax = 7.75, aw = W - X0 - ax, am = om.amenities || {};
  const lists = [["Community amenities", am.community], ["Unit amenities", am.unit]].filter(([, v]) => (v || []).length);
  let ay = 1.6;
  if (lists.length) {
    const ah = 0.45 + lists.reduce((a, [, v]) => a + 0.45 + 0.27 * v.length, 0);
    card(s, ax, ay, aw, ah);
    let y = ay + 0.25;
    for (const [h, list] of lists) {
      eyebrow(s, h, ax + 0.3, y, aw - 0.6, PRIMARY);
      T(s, list.map((t) => ({ text: t, options: { breakLine: true } })), { x: ax + 0.3, y: y + 0.32, w: aw - 0.6, h: 0.27 * list.length, fontSize: 11.5, color: INK, paraSpaceAfter: 3 });
      y += 0.45 + 0.27 * list.length;
    }
    ay += ah + 0.2;
  }
  const mh = 6.6 - ay;
  if (om.map && om.map.path) s.addImage({ path: om.map.path, x: ax, y: ay, w: aw, h: mh, sizing: { type: "contain", w: aw, h: mh }, altText: "Location map" });
  else { if (mh > 1.4) placeholderBox(s, ax, ay, aw, mh, "Location map", "Add a site or location map."); placeholders.push("Location map."); }
  source(s, "Radix deal record and rent roll. Amenities and map supplied by the broker.");
}
{
  const more = photos.slice(1, 5);
  const s = content("Property photos", section("The property"));
  if (more.length) {
    const g = 0.2, cols = more.length === 1 ? 1 : 2, rowsN = Math.ceil(more.length / cols);
    const pw = (CW - g * (cols - 1)) / cols, ph = (5.0 - g * (rowsN - 1)) / rowsN;
    more.forEach((p, i) => s.addImage({ path: p.path, x: X0 + (i % cols) * (pw + g), y: 1.6 + Math.floor(i / cols) * (ph + g), w: pw, h: ph, sizing: { type: "cover", w: pw, h: ph }, altText: p.caption || "Property photo" }));
  } else {
    placeholderBox(s, X0, 1.6, CW, 5.0, "Property photos", "Add exterior, amenity and unit interior photos.");
    placeholders.push("Property photos.");
  }
}
const drawSection = (name) => { for (const b of rendered) if (sectionOf[b] === name) B.draw[b](); };
drawSection("The property");

// ===== 4. Financial analysis
divider("Financial analysis", 2, blocksIn("Financial analysis"));
drawSection("Financial analysis");

// ===== 5. Market
divider("Market", 3, blocksIn("Market").concat(["Sales comparables", "Market overview"]));
drawSection("Market");
{
  const sc = om.sales_comps || {};
  const s = content("Sales comparables", section("Market"), sc.rows && sc.rows.length ? `${sc.rows.length} sales` : null);
  if ((sc.rows || []).length) {
    const rows = sc.rows.map((r) => ({ cells: [`${r.name}${r.city ? `, ${r.city}` : ""}`, r.sale_date ? dateLabel(r.sale_date) : "-", int(r.units), r.year_built ? String(r.year_built) : "-",
      money(r.price), isNum(r.price_per_unit) ? money(r.price_per_unit) : (isNum(r.price) && r.units ? money(r.price / r.units) : "-"), isNum(r.cap_rate) ? pct(r.cap_rate, 2) : "-"] }));
    table(s, ["Property", "Sale date", "Units", "Year built", "Price", "Price per unit", "Cap rate"], rows, { x: X0, y: 1.6, w: CW, colW: B.evenCols(CW, 3.6, 6), fontSize: 11, rowH: Math.min(0.45, 5.0 / (rows.length + 1)) });
    source(s, sc.source || "Sales comparables as supplied.");
    check("Every sales comp has a sale date and price", sc.rows.every((r) => r.sale_date && isNum(r.price)));
    check("Sales comps name their source", !!sc.source);
  } else {
    placeholderBox(s, X0, 1.6, CW, 5.0, "Sales comparables", "Radix doesn't hold sales comps yet. Add recent sales with price, price per unit and cap rate, or ask Claude to research them.");
    placeholders.push("Sales comparables.");
  }
}
{
  const mo = om.market_overview || {};
  const s = content("Market overview", section("Market"), deal.market);
  if ((mo.points || []).length) {
    const pts = mo.points.slice(0, 8), rh = Math.min(0.62, 5.0 / pts.length);
    pts.forEach((p, i) => {
      const y = 1.6 + i * rh;
      hair(s, X0, y, CW);
      T(s, String(i + 1).padStart(2, "0"), { x: X0, y: y + 0.12, w: 0.6, h: 0.35, fontSize: 14, fontFace: DISPLAY, color: PRIMARY });
      T(s, p.text, { x: X0 + 0.75, y: y + 0.12, w: CW - 0.75, h: rh - 0.15, fontSize: 13, color: INK });
    });
    source(s, `Sources: ${[...new Set(mo.points.map((p) => p.source))].join("; ")}`);
    check("Every market point names its source", mo.points.every((p) => p.source));
  } else {
    placeholderBox(s, X0, 1.6, CW, 5.0, "Market overview", "Add the submarket story: population and job growth, major employers and new supply. Claude can research it with sources.");
    placeholders.push("Market overview.");
  }
}

// ===== 6. Contacts and disclaimer
{
  const s = content("Contacts", section("Contacts"), firm);
  const lines = (brand.firm || {}).contact_lines || [];
  if (lines.length) {
    const cw = (CW - 0.4) / 3;
    lines.slice(0, 6).forEach((l, i) => {
      const parts = String(l).split(/\s+·\s+/), x = X0 + (i % 3) * (cw + 0.2), y = 1.6 + Math.floor(i / 3) * 1.75;
      card(s, x, y, cw, 1.55);
      T(s, parts[0], { x: x + 0.3, y: y + 0.25, w: cw - 0.6, h: 0.45, fontSize: 16, fontFace: DISPLAY, color: INK });
      T(s, parts.slice(1).join("\n"), { x: x + 0.3, y: y + 0.75, w: cw - 0.6, h: 0.7, fontSize: 10.5, color: MUTED });
    });
  } else { placeholderBox(s, X0, 1.6, CW, 2.9, "Broker team", "Add names, titles, phone and email (firm.contact_lines in brand.json)."); placeholders.push("Broker contacts."); }
  hair(s, X0, 5.05, CW);
  eyebrow(s, "Confidentiality and disclaimer", X0, 5.2, CW);
  T(s, brand.om_disclaimer || "", { x: X0, y: 5.5, w: CW, h: 1.2, fontSize: 9, color: FAINT });
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
