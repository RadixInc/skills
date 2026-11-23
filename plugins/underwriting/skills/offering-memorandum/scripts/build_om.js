#!/usr/bin/env node
/*
 * Build an Offering Memorandum as an editable PowerPoint deck from om.json (radix.om/v1)
 * and a brand profile (radix.brand_profile/v1).
 *
 *   node build_om.js --om om.json --brand brand.json --out OUTDIR [--pdf] [--force]
 *
 * Everything that must look and compute the same on every run lives here: derived figures,
 * the accuracy gate, layouts, tables and native charts. The agent only gathers data and drafts text.
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
const omPath = arg("--om"), outDir = arg("--out");
const brandPath = arg("--brand", path.join(__dirname, "..", "assets", "brand-radix-default.json"));
if (!omPath || !outDir) { console.error("usage: node build_om.js --om om.json --brand brand.json --out OUTDIR [--pdf] [--force]"); process.exit(1); }
const om = JSON.parse(fs.readFileSync(omPath, "utf8"));
const brand = JSON.parse(fs.readFileSync(brandPath, "utf8"));
if (om.schema !== "radix.om/v1") { console.error(JSON.stringify({ status: "error", error: "om.json must use schema radix.om/v1" })); process.exit(1); }

// ---------- formatting ----------
const isNum = (v) => typeof v === "number" && isFinite(v);
const money = (v, dp = 0) => !isNum(v) ? "-" : (v < 0 ? "(" : "") + "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp }) + (v < 0 ? ")" : "");
const compact = (v) => {
  if (!isNum(v)) return "-";
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e4) return `${s}$${Math.round(a / 1e3)}K`;
  return `${s}$${Math.round(a).toLocaleString("en-US")}`;
};
const pct = (v, dp = 1) => !isNum(v) ? "-" : `${v.toFixed(dp)}%`;          // percent number: 76.4
const ratio = (v, dp = 1) => !isNum(v) ? "-" : `${(v * 100).toFixed(dp)}%`; // ratio: 0.764
const int = (v) => !isNum(v) ? "-" : Math.round(v).toLocaleString("en-US");
const signedCompact = (v) => !isNum(v) ? "-" : (Math.abs(v) < 1 ? "$0" : (v > 0 ? "+" : "-") + compact(Math.abs(v)));
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dateLabel = (d, short) => {
  if (!d) return "";
  const [y, m, dd] = String(d).slice(0, 10).split("-").map(Number);
  return short ? `${MONTHS[m - 1]} ${y}` : `${MONTHS[m - 1]} ${dd}, ${y}`;
};
const ym = (s) => { const [y, m] = s.split("-").map(Number); return `${MONTHS[m - 1]} ${String(y).slice(2)}`; };

// Every figure the deck prints, so drafted text can be checked against it.
const shown = new Set();
const S = (txt) => { if (txt && txt !== "-") { shown.add(txt.replace(/[()]/g, "")); } return txt; };
const SM = (v) => {
  if (isNum(v)) {
    const a = Math.abs(v);
    S(money(a)); S(compact(a));
    for (const [u, d] of [["M", 1e6], ["K", 1e3]]) if (a >= d) for (const dp of [0, 1, 2]) S(`$${(a / d).toFixed(dp)}${u}`);
  }
  return money(v);
};

// ---------- brand ----------
const hex = (c, d) => (typeof c === "string" && /^#[0-9a-fA-F]{6}$/.test(c) ? c.slice(1).toUpperCase() : d);
const colors = brand.colors || {};
const PRIMARY = hex(colors.primary, "144A85"), ACCENT = hex(colors.accent, "1F76D6"), TINT = hex(colors.accent_tint, "EFF4FE");
const INK = "181D27", STRONG = "252B37", MUTED = "414651", FAINT = "717680", HUSH = "A4A7AE", RULE = "EAEAF0", CANVAS = "F5F5FA", WARN = "B54708", WARN_BG = "FFFAEB";
// Decks are opened on the reader's machine, so use a font every Office install has.
const DECK_SAFE = ["Arial", "Calibri", "Cambria"];
const FONT = DECK_SAFE.includes((brand.fonts || {}).body) ? brand.fonts.body : "Arial";
const firm = (brand.firm || {}).display_name || (brand.logo || {}).wordmark_text || "";

// ---------- data ----------
const deal = om.deal || {}, src = om.sources || {}, act = om.actuals || {}, pf = om.proforma || null;
const snap = om.snapshot || {}, units = deal.units;
const REV = [["potential_rent", "Potential rent"], ["loss_to_lease", "Loss to lease"], ["vacancy_credit", "Vacancy and credit loss"], ["other_income", "Other income"]];
const EXP = [["controllable", "Controllable expenses"], ["utilities", "Utilities"], ["taxes_insurance", "Taxes and insurance"], ["management", "Management fee"]];
const cols = act.columns || [];
const lines = (act.revenue || []).concat(act.expenses || []);
const groupSum = (g, k) => { const vs = lines.filter((l) => l.group === g).map((l) => l.values[k]).filter(isNum); return vs.length ? vs.reduce((a, b) => a + b, 0) : null; };
const groups = {}; for (const [g] of REV.concat(EXP)) { groups[g] = {}; for (const c of cols) groups[g][c.key] = groupSum(g, c.key); }
const actualOf = (key, col) => (["egr", "opex", "noi"].includes(key) ? (act[key] || {})[col] : groups[key][col]);
const pfOf = (key) => (!pf ? null : ["egr", "opex", "noi"].includes(key) ? pf[key] : (pf.groups || {})[key]);

// ---------- accuracy gate ----------
const checks = [], placeholders = [];
const check = (name, ok, detail = "") => checks.push({ check: name, ok: !!ok, detail });
const TOL = 1;
for (const c of cols) {
  const k = c.key;
  const rev = (act.revenue || []).reduce((a, r) => a + (r.values[k] || 0), 0);
  const exp = (act.expenses || []).reduce((a, r) => a + (r.values[k] || 0), 0);
  const egr = (act.egr || {})[k], opex = (act.opex || {})[k], noi = (act.noi || {})[k];
  if (isNum(egr)) check(`Actual ${k}: revenue lines sum to EGR`, Math.abs(rev - egr) <= TOL, `${rev.toFixed(2)} vs ${egr}`);
  if (isNum(opex)) check(`Actual ${k}: expense lines sum to OpEx`, Math.abs(exp - opex) <= TOL, `${exp.toFixed(2)} vs ${opex}`);
  if ([egr, opex, noi].every(isNum)) check(`Actual ${k}: NOI = EGR - OpEx`, Math.abs(egr - opex - noi) <= TOL);
}
check("Every actual line has a group", lines.every((l) => l.group), lines.filter((l) => !l.group).map((l) => l.label).join(", "));
if (pf) {
  const g = pf.groups || {};
  const r = REV.reduce((a, [k]) => a + (g[k] || 0), 0), e = EXP.reduce((a, [k]) => a + (g[k] || 0), 0);
  check("Pro forma: revenue groups sum to EGR", Math.abs(r - pf.egr) <= TOL, `${r} vs ${pf.egr}`);
  check("Pro forma: expense groups sum to OpEx", Math.abs(e - pf.opex) <= TOL, `${e} vs ${pf.opex}`);
  check("Pro forma: NOI = EGR - OpEx", Math.abs(pf.egr - pf.opex - pf.noi) <= TOL);
  const hn = (om.hold_cash_flow || {}).noi || [];
  if (hn.length) check("Pro forma Y1 NOI matches the cash flow's Y1", Math.abs(hn[0] - pf.noi) <= TOL);
}
const fp = om.floor_plans || {}, bd = om.bedrooms || {};
if (fp.rows) check("Floor plans add to the deal unit count", fp.rows.reduce((a, r) => a + (r.units || 0), 0) === units);
if (bd.rows) check("Bedroom summary adds to the deal unit count", bd.rows.reduce((a, r) => a + (r.units || 0), 0) === units);
if (isNum(snap.occupancy_pct) && bd.total && isNum(bd.total.occupied_pct)) check("Occupancy matches the rent roll total", Math.abs(snap.occupancy_pct - bd.total.occupied_pct) < 0.05);
check("Rent roll as-of date is stated", !!(src.rent_roll || {}).as_of);
check("Actual column windows are stated", cols.every((c) => c.window));
if (pf || om.hold_cash_flow) check("Client model file is named", !!(src.client_model || {}).file);

// ---------- deck ----------
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.title = `${deal.name || "Property"} Offering Memorandum`;
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
const W = 13.333, X0 = 0.6, CW = W - 2 * X0;
const footer = `${deal.name || ""} · Offering Memorandum`;

pres.defineSlideMaster({
  title: "OM_CONTENT",
  background: { color: "FFFFFF" },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.38, w: CW, h: 0.7, fontFace: FONT, fontSize: 26, bold: true, color: STRONG, align: "left", valign: "top", margin: 0 }, text: "" } },
    { text: { text: footer, options: { x: X0, y: 7.0, w: 7, h: 0.3, fontFace: FONT, fontSize: 9, color: FAINT, margin: 0 } } },
    { text: { text: firm, options: { x: W - X0 - 4.6, y: 7.0, w: 4, h: 0.3, fontFace: FONT, fontSize: 10, bold: true, color: PRIMARY, align: "right", margin: 0 } } },
  ],
  slideNumber: { x: W - X0 - 0.45, y: 7.0, w: 0.45, h: 0.3, fontFace: FONT, fontSize: 9, color: FAINT, align: "right" },
});
pres.defineSlideMaster({ title: "OM_COVER", background: { color: PRIMARY }, objects: [] });

const sections = new Set();
const section = (t) => { if (!sections.has(t)) { pres.addSection({ title: t }); sections.add(t); } return t; };
const content = (title, sec) => {
  const s = pres.addSlide({ masterName: "OM_CONTENT", sectionTitle: section(sec) });
  s.addText(title, { placeholder: "title", align: "left" });
  return s;
};
const T = (s, text, o) => s.addText(text, Object.assign({ fontFace: FONT, color: INK, margin: 0, isTextBox: true, valign: "top" }, o));
const note = (s, text, y) => T(s, text, { x: X0, y: y || 6.62, w: CW, h: 0.3, fontSize: 10, color: FAINT });

// Table helper: rows of cells, first column left, rest right; header row and optional total rows.
function table(s, header, rows, o) {
  const fs_ = o.fontSize || 11;
  const head = header.map((h, i) => ({ text: h, options: { bold: true, color: FAINT, fill: { color: CANVAS }, align: i ? "right" : "left", fontSize: fs_ - 1 } }));
  const body = rows.map((r) => r.cells.map((c, i) => ({
    text: c, options: { align: i ? "right" : "left", bold: !!r.bold, color: r.muted ? FAINT : INK, fill: { color: r.fill || "FFFFFF" }, fontSize: fs_ },
  })));
  s.addTable([head].concat(body), {
    x: o.x, y: o.y, w: o.w, colW: o.colW, fontFace: FONT, fontSize: fs_, color: INK, valign: "middle",
    border: { type: "solid", pt: 0.5, color: RULE }, rowH: o.rowH || 0.3, margin: [0.03, 0.08, 0.03, 0.08], autoPage: false,
  });
}
function placeholderBox(s, x, y, w, h, title, body) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: WARN_BG }, line: { color: "FEDF89", width: 1, dashType: "dash" } });
  T(s, [{ text: title, options: { bold: true, color: WARN, fontSize: 16, align: "center", breakLine: true } }, { text: body, options: { color: MUTED, fontSize: 13, align: "center" } }],
    { x: x + 0.5, y: y + 0.25, w: w - 1.0, h: h - 0.5, valign: "middle", align: "center", paraSpaceAfter: 6 });
}
const chartBase = () => ({
  fontFace: FONT, catAxisLabelFontFace: FONT, valAxisLabelFontFace: FONT, dataLabelFontFace: FONT, legendFontFace: FONT,
  catAxisLabelColor: FAINT, valAxisLabelColor: FAINT, catAxisLabelFontSize: 10, valAxisLabelFontSize: 9,
  valGridLine: { color: RULE, size: 0.5 }, catGridLine: { style: "none" }, catAxisLineShow: true, catAxisLineColor: "D5D7DA",
  dataLabelColor: MUTED, dataLabelFontSize: 9, legendColor: MUTED, legendFontSize: 10,
});

for (const tok of String(deal.address || "").match(/\d+/g) || []) shown.add(tok);

// ===== 1. Cover
{
  const s = pres.addSlide({ masterName: "OM_COVER", sectionTitle: section("Cover") });
  T(s, "OFFERING MEMORANDUM", { x: X0, y: 0.8, w: 6, h: 0.35, fontSize: 12, bold: true, color: "FFFFFF", charSpacing: 3 });
  T(s, deal.name || "", { x: X0, y: 2.3, w: 6.4, h: 1.3, fontSize: 44, bold: true, color: "FFFFFF", valign: "bottom" });
  T(s, deal.address || "", { x: X0, y: 3.7, w: 6.4, h: 0.4, fontSize: 16, color: "FFFFFF" });
  const facts = [isNum(units) ? `${S(int(units))} units` : null, deal.year_built ? `Built ${deal.year_built}` : null, deal.building_type || null].filter(Boolean).join("  ·  ");
  T(s, facts, { x: X0, y: 4.15, w: 6.4, h: 0.4, fontSize: 14, color: "DBE6FC" });
  T(s, firm, { x: X0, y: 6.5, w: 5, h: 0.45, fontSize: 18, bold: true, color: "FFFFFF" });
  if ((om.photos || []).length) {
    s.addImage({ path: om.photos[0].path, x: 7.4, y: 0, w: W - 7.4, h: 7.5, sizing: { type: "cover", w: W - 7.4, h: 7.5 }, altText: om.photos[0].caption || "Property photo" });
  } else {
    s.addShape(pres.shapes.RECTANGLE, { x: 7.4, y: 0, w: W - 7.4, h: 7.5, fill: { color: "1A5A9E" }, line: { type: "none" } });
    T(s, "Property photo\nAdd the hero image here", { x: 7.4, y: 3.2, w: W - 7.4, h: 1.0, fontSize: 14, color: "BACFF9", align: "center", valign: "middle" });
    placeholders.push("Cover photo.");
  }
}

// ===== 2. Executive summary
{
  const s = content("Executive summary", "Offering");
  T(s, S(om.summary || ""), { x: X0, y: 1.3, w: 7.3, h: 1.3, fontSize: 14, color: INK, valign: "top", paraSpaceAfter: 6 });
  // highlights as titled rows
  let y = 2.75;
  for (const h of om.highlights || []) {
    s.addShape(pres.shapes.OVAL, { x: X0, y: y + 0.06, w: 0.22, h: 0.22, fill: { color: PRIMARY }, line: { type: "none" } });
    T(s, [{ text: h.title + "\n", options: { bold: true, fontSize: 14, color: STRONG } }, { text: h.text, options: { fontSize: 12, color: MUTED } }],
      { x: X0 + 0.4, y, w: 6.9, h: 0.9 });
    y += 0.95;
  }
  // offering terms + stats
  const ox = 8.4, ow = W - X0 - ox;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: ox, y: 1.3, w: ow, h: 2.2, rectRadius: 0.08, fill: { color: CANVAS }, line: { color: RULE, width: 0.75 } });
  T(s, "Offering", { x: ox + 0.25, y: 1.45, w: ow - 0.5, h: 0.35, fontSize: 13, bold: true, color: STRONG });
  const off = om.offering || {};
  const termRows = [["Price", isNum(off.price) ? SM(off.price) : off.price_label || "Unpriced"], ["Offers due", off.offers_due ? dateLabel(off.offers_due) : "To be announced"]]
    .concat((off.terms || []).map((t) => [t.label, t.value]));
  if (!isNum(off.price) && !off.price_label) placeholders.push("Offering price or 'Unpriced'.");
  if (!off.offers_due) placeholders.push("Offer due date.");
  let ty = 1.9;
  for (const [a, b] of termRows) {
    T(s, a, { x: ox + 0.25, y: ty, w: 1.6, h: 0.3, fontSize: 12, color: FAINT });
    T(s, b, { x: ox + 1.9, y: ty, w: ow - 2.15, h: 0.3, fontSize: 12, bold: true, color: INK });
    ty += 0.36;
  }
  const stats = [["Units", S(int(units))], ["Occupancy", S(pct(snap.occupancy_pct))], ["Avg in-place rent", SM(snap.in_place_rent)], ["T12 NOI", S(compact((act.noi || {}).T12))]];
  SM((act.noi || {}).T12);
  stats.forEach(([label, val], i) => {
    const sx = ox + (i % 2) * (ow / 2 + 0.05), sy = 3.75 + Math.floor(i / 2) * 1.35, sw = ow / 2 - 0.05;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: sx, y: sy, w: sw, h: 1.2, rectRadius: 0.08, fill: { color: "FFFFFF" }, line: { color: RULE, width: 0.75 } });
    T(s, label, { x: sx + 0.2, y: sy + 0.18, w: sw - 0.4, h: 0.3, fontSize: 12, color: MUTED });
    T(s, val, { x: sx + 0.2, y: sy + 0.5, w: sw - 0.4, h: 0.55, fontSize: 26, bold: true, color: PRIMARY });
  });
  s.addNotes("Summary and highlights are drafted from Radix data. Edit them before sending.");
}

// ===== 3. Property overview
{
  const s = content("Property overview", "Property");
  const rows = [["Address", deal.address], ["Market", deal.market], ["Year built", deal.year_built ? String(deal.year_built) : null], ["Building type", deal.building_type],
    ["Units", S(int(units))], ["Rentable SF", deal.total_sf ? S(int(deal.total_sf)) : null], ["Average unit size", bd.total ? `${S(int(bd.total.avg_sf))} SF` : null],
    ["Occupancy", `${S(pct(snap.occupancy_pct))}${isNum(snap.vacant_units) ? `, ${S(int(snap.vacant_units))} vacant units,` : ""} on the ${dateLabel((src.rent_roll || {}).as_of)} rent roll`]].filter((r) => r[1]);
  let y = 1.35;
  for (const [a, b] of rows) {
    T(s, a, { x: X0, y, w: 2.2, h: 0.4, fontSize: 14, color: FAINT });
    T(s, b, { x: X0 + 2.3, y, w: 4.2, h: 0.4, fontSize: 14, bold: true, color: INK });
    s.addShape(pres.shapes.LINE, { x: X0, y: y + 0.5, w: 6.5, h: 0, line: { color: RULE, width: 0.75 } });
    y += 0.62;
  }
  if (om.map && om.map.path) s.addImage({ path: om.map.path, x: 7.5, y: 1.35, w: 5.23, h: 5.1, altText: "Location map" });
  else { placeholderBox(s, 7.5, 1.35, 5.23, 5.1, "Location map", "Add a site or location map. Maps aren't generated yet."); placeholders.push("Location map."); }
}

// ===== 4. Unit mix by floor plan
if (fp.rows) {
  const s = content("Unit mix", "Property");
  const rows = fp.rows.map((r) => ({ cells: [r.plan, `${r.beds} / ${r.baths}`, S(int(r.units)), S(pct(100 * r.units / units)), S(int(r.avg_sf)), SM(r.market_rent),
    isNum(r.in_place_rent) ? SM(r.in_place_rent) : "-", isNum(r.market_rent) && r.avg_sf ? `$${(r.market_rent / r.avg_sf).toFixed(2)}` : "-", S(pct(r.occupied_pct))] }));
  const t = fp.total;
  rows.push({ bold: true, fill: CANVAS, cells: ["Total / avg", "", S(int(t.units)), "100.0%", S(int(t.avg_sf)), SM(t.market_rent), SM(t.in_place_rent), `$${(t.market_rent / t.avg_sf).toFixed(2)}`, S(pct(t.occupied_pct))] });
  table(s, ["Floor plan", "Bed / bath", "Units", "% of units", "Avg SF", "Market rent", "In-place rent", "Market $/SF", "Occupied"], rows,
    { x: X0, y: 1.3, w: CW, colW: [2.1, 1.2, 1.0, 1.2, 1.1, 1.45, 1.45, 1.3, 1.33], fontSize: 11, rowH: 0.33 });
  note(s, `Radix rent roll as of ${dateLabel((src.rent_roll || {}).as_of)}. Contractual rent. Market $/SF derived.`, 6.62);
}

// ===== 5. Rents vs market by bedroom
if (bd.rows) {
  const s = content("Rents and recent leasing", "Property");
  const labels = bd.rows.map((r) => r.label);
  s.addChart(pres.charts.BAR, [
    { name: "Market rent", labels, values: bd.rows.map((r) => Math.round(r.market_rent)) },
    { name: "In-place rent", labels, values: bd.rows.map((r) => Math.round(r.in_place_rent)) },
    { name: "Leases, last 90 days", labels, values: bd.rows.map((r) => Math.round(r.last90_rent || 0)) },
  ], Object.assign(chartBase(), {
    x: X0, y: 1.3, w: 6.6, h: 5.1, barDir: "col", barGapWidthPct: 60, chartColors: [PRIMARY, ACCENT, HUSH],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "$#,##0", valAxisLabelFormatCode: "$#,##0",
    showLegend: true, legendPos: "b", showTitle: true, title: "Average rent per unit per month", titleFontFace: FONT, titleFontSize: 12, titleColor: STRONG,
  }));
  const rows = bd.rows.map((r) => ({ cells: [r.label, S(int(r.units)), SM(r.market_rent), SM(r.in_place_rent), S(pct(r.pct_of_market)), isNum(r.last90_rent) ? SM(r.last90_rent) : "-", S(pct(r.occupied_pct))] }));
  const t = bd.total;
  rows.push({ bold: true, fill: CANVAS, cells: ["Total / avg", S(int(t.units)), SM(t.market_rent), SM(t.in_place_rent), S(pct(t.pct_of_market)), SM(t.last90_rent), S(pct(t.occupied_pct))] });
  const rw = W - X0 - 7.45;
  table(s, ["", "Units", "Market", "In-place", "% mkt", "Last 90d", "Occ."], rows,
    { x: 7.45, y: 1.3, w: rw, colW: [1.0, 0.6, 0.75, 0.75, 0.7, 0.75, rw - 4.55], fontSize: 11, rowH: 0.36 });
  T(s, "% mkt: in-place rent as a share of market rent. Last 90d: average rent on leases signed in the 90 days before the rent roll date. Occ.: occupied units.", { x: 7.45, y: 3.65, w: rw, h: 0.8, fontSize: 10, color: FAINT });
  note(s, `Radix rent roll as of ${dateLabel((src.rent_roll || {}).as_of)}. Contractual rent.`, 6.62);
}

// ===== 6. Operating history (monthly)
const m = act.monthly || {};
if ((m.noi || []).length) {
  const s = content("Operating history", "Financials");
  const labels = (m.months || []).map(ym);
  s.addChart(pres.charts.LINE, [
    { name: "Effective gross revenue", labels, values: m.egr.map(Math.round) },
    { name: "Operating expenses", labels, values: m.opex.map(Math.round) },
    { name: "Net operating income", labels, values: m.noi.map(Math.round) },
  ], Object.assign(chartBase(), {
    x: X0, y: 1.3, w: 7.2, h: 5.1, chartColors: [ACCENT, HUSH, PRIMARY], lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 5,
    valAxisLabelFormatCode: "$#,##0", showLegend: true, legendPos: "b", showTitle: true, title: "By month, T12", titleFontFace: FONT, titleFontSize: 12, titleColor: STRONG,
  }));
  const rowsDef = [["egr", "Effective gross revenue"], ["opex", "Operating expenses"], ["noi", "Net operating income"]];
  const rows = rowsDef.map(([k, l]) => ({ bold: k === "noi", fill: k === "noi" ? TINT : undefined, cells: [l].concat(cols.map((c) => SM((act[k] || {})[c.key]))) }));
  rows.push({ muted: true, cells: ["NOI per unit"].concat(cols.map((c) => SM((act.noi || {})[c.key] / units))) });
  table(s, ["$ annual"].concat(cols.map((c) => c.label)), rows, { x: 8.1, y: 1.3, w: W - X0 - 8.1, colW: (() => { const tw = W - X0 - 8.1, first = 1.75, rest = (tw - first) / cols.length; return [first].concat(Array(cols.length).fill(rest)); })(), fontSize: 11, rowH: 0.4 });
  T(s, cols.map((c) => `${c.label}: ${c.window}`).join("\n"), { x: 8.1, y: 3.5, w: W - X0 - 8.1, h: 0.9, fontSize: 10, color: FAINT });
  note(s, "Radix operating statement, actuals. T3 and T1 are annualized.", 6.62);
}

// ===== 7. Financial analysis: T12 to Year 1 pro forma
{
  const s = content("Financial analysis", "Financials");
  const header = ["$ annual"].concat(cols.map((c) => c.label)).concat(pf ? [pf.label || "Year 1 pro forma", "Per unit", "Change vs T12"] : []);
  const mk = (key, label, opt = {}) => {
    const cells = [label].concat(cols.map((c) => SM(actualOf(key, c.key))));
    if (pf) {
      const p = pfOf(key), a = actualOf(key, "T12");
      SM(p); SM(isNum(p) && isNum(a) ? p - a : null);
      cells.push(SM(p), isNum(p) && units ? SM(p / units) : "-", S(signedCompact(isNum(p) && isNum(a) ? p - a : null)));
    }
    return Object.assign({ cells }, opt);
  };
  const sec = (t) => ({ bold: true, muted: true, fill: CANVAS, cells: [t].concat(Array(header.length - 1).fill("")) });
  const rows = [sec("Revenue")].concat(REV.map(([k, l]) => mk(k, l)), [mk("egr", "Effective gross revenue", { bold: true }), sec("Operating expenses")],
    EXP.map(([k, l]) => mk(k, l)), [mk("opex", "Total operating expenses", { bold: true }), mk("noi", "Net operating income", { bold: true, fill: TINT })]);
  const n = header.length;
  const first = 3.0, rest = (CW - first) / (n - 1);
  table(s, header, rows, { x: X0, y: 1.3, w: CW, colW: [first].concat(Array(n - 1).fill(rest)), fontSize: 11, rowH: 0.34 });
  if (!pf) placeholders.push("Pro forma (needs the client model).");
  note(s, `Actuals from the Radix operating statement (${cols.map((c) => `${c.label} ${c.window}`).join("; ")}).` + (pf ? ` Pro forma from ${(src.client_model || {}).file}.` : "") + " Groups, per-unit figures and changes derived.", 6.45);
}

// ===== 8. Pro forma cash flow
const hcf = om.hold_cash_flow || {};
if ((hcf.noi || []).length) {
  const s = content("Pro forma cash flow", "Financials");
  const years = hcf.years || hcf.noi.map((_, i) => `Year ${i + 1}`);
  s.addChart(pres.charts.BAR, [{ name: "Net operating income", labels: years, values: hcf.noi.map(Math.round) }], Object.assign(chartBase(), {
    x: X0, y: 1.3, w: CW, h: 3.0, barDir: "col", barGapWidthPct: 70, chartColors: [PRIMARY], showValue: true, dataLabelPosition: "outEnd", valAxisMinVal: 0,
    dataLabelFormatCode: "$#,##0", valAxisLabelFormatCode: "$#,##0", showLegend: false, showTitle: true, title: "Net operating income by year", titleFontFace: FONT, titleFontSize: 12, titleColor: STRONG,
  }));
  const rows = [["egr", "Effective gross revenue"], ["opex", "Operating expenses"], ["noi", "Net operating income"]].filter(([k]) => hcf[k])
    .map(([k, l]) => ({ bold: k === "noi", fill: k === "noi" ? TINT : undefined, cells: [l].concat(hcf[k].map((v) => (k === "opex" ? `(${SM(v).replace("$", "$")})` : SM(v)))) }));
  const n = years.length + 1, first = 2.6;
  table(s, ["$"].concat(years), rows, { x: X0, y: 4.5, w: CW, colW: [first].concat(Array(n - 1).fill((CW - first) / (n - 1))), fontSize: 11, rowH: 0.36 });
  note(s, `From ${(src.client_model || {}).file || "the client model"}.`, 6.45);
}

// ===== 12. Underwriting assumptions
if ((om.assumptions || []).length) {
  const s = content("Pro forma assumptions", "Financials");
  let y = 1.35;
  for (const a of om.assumptions) {
    T(s, a.label, { x: X0, y, w: 3.4, h: 0.45, fontSize: 14, color: FAINT });
    T(s, a.value, { x: X0 + 3.5, y, w: CW - 3.5, h: 0.45, fontSize: 14, bold: true, color: INK });
    s.addShape(pres.shapes.LINE, { x: X0, y: y + 0.55, w: CW, h: 0, line: { color: RULE, width: 0.75 } });
    y += 0.68;
  }
  note(s, `From ${(src.client_model || {}).file || "the client model"}.`, 6.45);
}

// ===== 9. Rent comparables
const comps = om.comps;
if (comps && (comps.deals || []).length) {
  const s = content("Rent comparables", "Market");
  const beds = ["Studio", "1 Bed", "2 Bed", "3 Bed"];
  const subj = {}; for (const r of bd.rows || []) subj[r.label] = r;
  const deals = comps.deals;
  const present = beds.filter((b) => subj[b] || deals.some((d) => d.rows.some((r) => r.label === b)));
  const chartBeds = present.filter((b) => subj[b]);
  s.addChart(pres.charts.BAR, [{ name: `${(comps.subject || {}).name || deal.name} (subject)`, labels: chartBeds, values: chartBeds.map((b) => Math.round(subj[b].in_place_rent)) }]
    .concat(deals.map((d) => ({ name: d.name, labels: chartBeds, values: chartBeds.map((b) => { const r = d.rows.find((x) => x.label === b); return r ? Math.round(r.in_place_rent) : 0; }) }))),
    Object.assign(chartBase(), { x: X0, y: 1.3, w: 5.6, h: 5.0, barDir: "col", barGapWidthPct: 60, chartColors: [PRIMARY, HUSH, ACCENT, "D5D7DA"],
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "$#,##0", valAxisLabelFormatCode: "$#,##0", showLegend: true, legendPos: "b",
      showTitle: true, title: "Average in-place rent by bedroom", titleFontFace: FONT, titleFontSize: 12, titleColor: STRONG }));
  const rows = [];
  const addProp = (name, sub, rowsBy, total, fill) => {
    rows.push({ bold: true, fill: fill || CANVAS, cells: [`${name} · rent roll ${sub}`, "", "", "", "", ""] });
    for (const b of present) {
      const r = rowsBy[b]; if (!r) continue;
      rows.push({ cells: [`   ${b}`, S(int(r.units)), S(int(r.avg_sf)), SM(r.market_rent), SM(r.in_place_rent), S(pct(r.occupied_pct))] });
    }
    if (total) rows.push({ bold: true, cells: ["   Total / avg", S(int(total.units)), S(int(total.avg_sf)), SM(total.market_rent), SM(total.in_place_rent), S(pct(total.occupied_pct))] });
  };
  addProp(`${(comps.subject || {}).name || deal.name} (subject)`, dateLabel((comps.subject || {}).as_of, false), subj, bd.total, TINT);
  for (const d of deals) { const by = {}; for (const r of d.rows) by[r.label] = r; addProp(`${d.name}, ${d.city}`, dateLabel(d.as_of), by, d.total); }
  const tx = 6.5, tw = W - X0 - tx;
  table(s, ["Property / unit type", "Units", "Avg SF", "Market", "In-place", "Occupied"], rows,
    { x: tx, y: 1.3, w: tw, colW: [2.55, 0.65, 0.7, 0.8, 0.8, tw - 5.5], fontSize: 10, rowH: 0.3 });
  note(s, comps.source || "Radix rent comp set.", 6.45);
  if (deals.length < 3) placeholders.push(`Rent comps: only ${deals.length} comparable propert${deals.length === 1 ? "y" : "ies"} in Radix for this market. Add more from Radix Market Comps or broker research.`);
} else {
  const s = content("Rent comparables", "Market");
  placeholderBox(s, X0, 1.4, CW, 4.9, "Rent comparables", "No comparable properties with recent rent rolls in Radix for this market.");
  placeholders.push("Rent comparables.");
}

// ===== 10. Sales comparables
{
  const s = content("Sales comparables", "Market");
  if (om.sales_comps && (om.sales_comps.rows || []).length) {
    const rows = om.sales_comps.rows.map((r) => ({ cells: [r.name, r.city || "", r.sale_date ? dateLabel(r.sale_date, true) : "-", r.units ? int(r.units) : "-", r.year_built ? String(r.year_built) : "-", SM(r.price), r.units && isNum(r.price) ? SM(r.price / r.units) : "-", isNum(r.cap_rate) ? ratio(r.cap_rate, 2) : "-"] }));
    table(s, ["Property", "City", "Sold", "Units", "Built", "Price", "Price / unit", "Cap rate"], rows, { x: X0, y: 1.3, w: CW, colW: [3.0, 1.6, 1.1, 0.9, 0.9, 1.7, 1.5, 1.43], fontSize: 11, rowH: 0.36 });
    note(s, om.sales_comps.source || "", 6.45);
  } else {
    placeholderBox(s, X0, 1.4, CW, 4.9, "Sales comparables", "Not in Radix yet. Add recent sales from broker research, or rerun with web research turned on.");
    placeholders.push("Sales comparables.");
  }
}

// ===== 11. Market overview
{
  const s = content("Market overview", "Market");
  if (om.market_overview && om.market_overview.text) {
    T(s, om.market_overview.text, { x: X0, y: 1.3, w: CW, h: 4.9, fontSize: 14, paraSpaceAfter: 8 });
    note(s, om.market_overview.source || "", 6.45);
  } else {
    placeholderBox(s, X0, 1.4, CW, 4.9, "Market overview", "Employment, population, supply pipeline and rent trends for the submarket. Coming from Radix Research; add the broker's market section in the meantime.");
    placeholders.push("Market overview.");
  }
}

// ===== 13. Contacts and confidentiality
{
  const s = content("Contacts and confidentiality", "Contacts");
  const contacts = om.contacts || [];
  if (contacts.length) {
    contacts.forEach((c, i) => {
      const x = X0 + (i % 3) * 4.1, y = 1.35 + Math.floor(i / 3) * 1.35;
      T(s, [{ text: c.name + "\n", options: { bold: true, fontSize: 14, color: STRONG } }, { text: [c.title, c.phone, c.email].filter(Boolean).join("\n"), options: { fontSize: 12, color: MUTED } }], { x, y, w: 3.9, h: 1.2 });
    });
  } else {
    placeholderBox(s, X0, 1.35, CW, 1.6, "Broker team", "Names, titles, phone numbers and email addresses. Save them once in the brand profile's contact lines.");
    placeholders.push("Broker contacts.");
  }
  T(s, brand.om_disclaimer || "This Offering Memorandum is confidential and was prepared to help prospective purchasers evaluate the property. It does not purport to be all-inclusive. Figures are drawn from the seller's rent roll and operating statements and from projections that may not be achieved. Prospective purchasers should conduct their own investigation.",
    { x: X0, y: 3.4, w: CW, h: 2.6, fontSize: 12, color: MUTED });
}

// ---------- narrative gate (summary and highlights must cite printed figures) ----------
const NUM = /\$?\(?-?\d[\d,]*(?:\.\d+)?\)?[%xMK]?/g;
const narrative = [["Summary", om.summary || ""]].concat((om.highlights || []).map((h, i) => [`Highlight ${i + 1}`, h.text]));
for (const [name, text] of narrative) {
  const bad = [];
  for (let tok of text.match(NUM) || []) {
    tok = tok.replace(/[.,;:]+$/, "").replace(/[()]/g, "");
    if (/^\d{1,2}$/.test(tok) || /^(19|20)\d\d$/.test(tok)) continue;
    if (!shown.has(tok)) bad.push(tok);
  }
  check(`${name}: every figure appears in the deck`, bad.length === 0, bad.join(", "));
}

// ---------- write ----------
const failed = checks.filter((c) => !c.ok);
const status = failed.length ? "fail" : placeholders.length ? "pass_with_placeholders" : "pass";
if (failed.length && !flag("--force")) { console.log(JSON.stringify({ status, failed }, null, 2)); process.exit(2); }
fs.mkdirSync(outDir, { recursive: true });
const stem = (deal.name || "Property").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "") + "-OM";
const pptxPath = path.join(outDir, `${stem}.pptx`);
pres.writeFile({ fileName: pptxPath }).then(async () => {
  // pptxgenjs writes folder entries into the ZIP; cloud editors refuse those. Repack without them.
  try {
    const JSZip = require(require.resolve("jszip", { paths: [path.dirname(require.resolve("pptxgenjs"))] }));
    const src = await JSZip.loadAsync(fs.readFileSync(pptxPath));
    const out = new JSZip();
    const names = Object.keys(src.files).filter((k) => !src.files[k].dir);
    // [Content_Types].xml first, then every file part; folder entries are dropped (remove() would delete their children too).
    names.sort((a, b) => (a === "[Content_Types].xml" ? -1 : b === "[Content_Types].xml" ? 1 : 0));
    for (const k of names) out.file(k, await src.files[k].async("nodebuffer"), { createFolders: false });
    const buf = await out.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
    if (names.length > 10) fs.writeFileSync(pptxPath, buf);
  } catch (e) { /* leave the file as written */ }
  const outputs = [pptxPath];
  if (flag("--pdf")) {
    const r = spawnSync("soffice", ["--headless", "--convert-to", "pdf", "--outdir", outDir, pptxPath], { timeout: 180000 });
    const pdf = path.join(outDir, `${stem}.pdf`);
    outputs.push(fs.existsSync(pdf) ? pdf : "PDF not written: LibreOffice (soffice) not available. Open the .pptx and save as PDF.");
  }
  const summary = [`# Run summary: ${deal.name} OM`, "", `Accuracy gate: **${status.replace(/_/g, " ")}**`, "", "## Checks"]
    .concat(checks.map((c) => `- ${c.ok ? "PASS" : "FAIL"}: ${c.check}${!c.ok && c.detail ? ` (${c.detail})` : ""}`), ["", "## Placeholders"], placeholders.length ? placeholders.map((p) => `- ${p}`) : ["- None"], ["", "## Files"], outputs.map((o) => `- ${o}`)).join("\n");
  fs.writeFileSync(path.join(outDir, `${stem}-run-summary.md`), summary + "\n");
  console.log(JSON.stringify({ status, outputs, placeholders, failed }, null, 2));
});
