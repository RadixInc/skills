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

// The catalog, in display order. Block ids are stable: users and saved defaults refer to them.
const CATALOG = ["property_snapshot", "unit_mix", "rents_vs_market", "operating_history", "operating_statement", "proforma_cash_flow", "proforma_assumptions", "rent_comps"];
const wanted = (data.blocks && data.blocks.length ? data.blocks : CATALOG);
const unknown = wanted.filter((b) => !CATALOG.includes(b));
if (unknown.length) { console.error(JSON.stringify({ status: "error", error: `Unknown block ids: ${unknown.join(", ")}`, catalog: CATALOG })); process.exit(1); }
const selected = CATALOG.filter((b) => wanted.includes(b));

// ---------- formatting (fixed: every block uses these) ----------
const isNum = (v) => typeof v === "number" && isFinite(v);
const money = (v, dp = 0) => !isNum(v) ? "-" : (v < 0 ? "(" : "") + "$" + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp }) + (v < 0 ? ")" : "");
const compact = (v) => {
  if (!isNum(v)) return "-";
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e4) return `${s}$${Math.round(a / 1e3)}K`;
  return `${s}$${Math.round(a).toLocaleString("en-US")}`;
};
const pct = (v, dp = 1) => !isNum(v) ? "-" : `${v.toFixed(dp)}%`; // percent number: 76.4
const int = (v) => !isNum(v) ? "-" : Math.round(v).toLocaleString("en-US");
const signedCompact = (v) => !isNum(v) ? "-" : (Math.abs(v) < 1 ? "$0" : (v > 0 ? "+" : "-") + compact(Math.abs(v)));
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const dateLabel = (d) => {
  if (!d) return "";
  const [y, m, dd] = String(d).slice(0, 10).split("-").map(Number);
  return `${MONTHS[m - 1]} ${dd}, ${y}`;
};
const ym = (s) => { const [y, m] = s.split("-").map(Number); return `${MONTHS[m - 1]} ${String(y).slice(2)}`; };

// ---------- brand (colors only; layout, type scale and neutrals are fixed) ----------
const hex = (c, d) => (typeof c === "string" && /^#[0-9a-fA-F]{6}$/.test(c) ? c.slice(1).toUpperCase() : d);
const colors = brand.colors || {};
const PRIMARY = hex(colors.primary, "144A85"), ACCENT = hex(colors.accent, "1F76D6"), TINT = hex(colors.accent_tint, "EFF4FE");
const INK = "181D27", STRONG = "252B37", MUTED = "414651", FAINT = "717680", HUSH = "A4A7AE", RULE = "EAEAF0", CANVAS = "F5F5FA";
// Blocks are pasted into the user's own files, so use a font every Office install has.
const DECK_SAFE = ["Arial", "Calibri", "Cambria"];
const FONT = DECK_SAFE.includes((brand.fonts || {}).body) ? brand.fonts.body : "Arial";

// ---------- data ----------
const deal = data.deal || {}, src = data.sources || {}, act = data.actuals || {}, pf = data.proforma || null;
const snap = data.snapshot || {}, units = deal.units;
const REV = [["potential_rent", "Potential rent"], ["loss_to_lease", "Loss to lease"], ["vacancy_credit", "Vacancy and credit loss"], ["other_income", "Other income"]];
const EXP = [["controllable", "Controllable expenses"], ["utilities", "Utilities"], ["taxes_insurance", "Taxes and insurance"], ["management", "Management fee"]];
const cols = act.columns || [];
const lines = (act.revenue || []).concat(act.expenses || []);
const groupSum = (g, k) => { const vs = lines.filter((l) => l.group === g).map((l) => l.values[k]).filter(isNum); return vs.length ? vs.reduce((a, b) => a + b, 0) : null; };
const groups = {}; for (const [g] of REV.concat(EXP)) { groups[g] = {}; for (const c of cols) groups[g][c.key] = groupSum(g, c.key); }
const actualOf = (key, col) => (["egr", "opex", "noi"].includes(key) ? (act[key] || {})[col] : groups[key][col]);
const pfOf = (key) => (!pf ? null : ["egr", "opex", "noi"].includes(key) ? pf[key] : (pf.groups || {})[key]);
// Unit mix is always by bed / bath (groupBy unitMixBath), never by floor plan.
const um = data.unit_mix || {};
const bathLabel = (b) => (Number.isInteger(b) ? String(b) : Number(b).toFixed(1));
const unitType = (r) => `${r.beds === 0 ? "Studio" : `${r.beds} bed`} / ${bathLabel(r.baths)} bath`;
const typeKey = (r) => `${r.beds}-${r.baths}`;
const rrDate = dateLabel((src.rent_roll || {}).as_of);
const modelFile = (src.client_model || {}).file;
const hcf = data.hold_cash_flow || {};
const m = act.monthly || {};
const comps = data.comps;

// What each block needs. A selected block without its data is skipped and reported, never drawn empty.
const needs = {
  property_snapshot: () => (isNum(units) && isNum(snap.occupancy_pct) ? null : "deal units and rent roll occupancy"),
  unit_mix: () => ((um.rows || []).length ? null : "a mapped rent roll"),
  rents_vs_market: () => ((um.rows || []).length ? null : "a mapped rent roll"),
  operating_history: () => ((m.noi || []).length ? null : "a mapped T12 with monthly columns"),
  operating_statement: () => (cols.length ? null : "a mapped T12"),
  proforma_cash_flow: () => ((hcf.noi || []).length ? null : "the client's model"),
  proforma_assumptions: () => ((data.assumptions || []).length ? null : "the client's model"),
  rent_comps: () => (comps && (comps.deals || []).length ? null : "comparable properties with recent rent rolls in Radix"),
};
const skipped = [], rendered = [];
for (const b of selected) { const n = needs[b](); if (n) skipped.push({ block: b, needs: n }); else rendered.push(b); }

// ---------- accuracy gate (only for the data the rendered blocks use) ----------
const checks = [];
const check = (name, ok, detail = "") => checks.push({ check: name, ok: !!ok, detail });
const TOL = 1;
const uses = (...b) => b.some((x) => rendered.includes(x));
if (uses("operating_history", "operating_statement")) {
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
  check("Actual column windows are stated", cols.every((c) => c.window));
}
if (uses("operating_statement", "proforma_cash_flow") && pf) {
  const g = pf.groups || {};
  const r = REV.reduce((a, [k]) => a + (g[k] || 0), 0), e = EXP.reduce((a, [k]) => a + (g[k] || 0), 0);
  check("Pro forma: revenue groups sum to EGR", Math.abs(r - pf.egr) <= TOL, `${r} vs ${pf.egr}`);
  check("Pro forma: expense groups sum to OpEx", Math.abs(e - pf.opex) <= TOL, `${e} vs ${pf.opex}`);
  check("Pro forma: NOI = EGR - OpEx", Math.abs(pf.egr - pf.opex - pf.noi) <= TOL);
  if ((hcf.noi || []).length) check("Pro forma Y1 NOI matches the cash flow's Y1", Math.abs(hcf.noi[0] - pf.noi) <= TOL);
}
if (uses("proforma_cash_flow")) {
  hcf.noi.forEach((n, i) => { if (isNum((hcf.egr || [])[i]) && isNum((hcf.opex || [])[i])) check(`Cash flow ${hcf.years[i]}: NOI = EGR - OpEx`, Math.abs(hcf.egr[i] - hcf.opex[i] - n) <= TOL); });
}
if (uses("unit_mix", "rents_vs_market", "rent_comps", "property_snapshot") && (um.rows || []).length) {
  check("Unit mix rows have beds and baths", um.rows.every((r) => isNum(r.beds) && isNum(r.baths)));
  check("Unit mix adds to the deal unit count", um.rows.reduce((a, r) => a + (r.units || 0), 0) === units, `${um.rows.reduce((a, r) => a + (r.units || 0), 0)} vs ${units}`);
  if (isNum(snap.occupancy_pct) && isNum((um.total || {}).occupied_pct)) check("Occupancy matches the rent roll total", Math.abs(snap.occupancy_pct - um.total.occupied_pct) < 0.05);
  check("Rent roll as-of date is stated", !!rrDate);
}
if (uses("rent_comps")) {
  for (const d of comps.deals) check(`Comp ${d.name}: rows add to its unit count`, d.rows.reduce((a, r) => a + (r.units || 0), 0) === (d.total || {}).units);
}
if (uses("proforma_cash_flow", "proforma_assumptions") || (uses("operating_statement") && pf)) check("Client model file is named", !!modelFile);

// ---------- deck: one block per slide, fixed frame ----------
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.title = `${deal.name || "Property"} · Radix data blocks`;
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };
const W = 13.333, X0 = 0.6, CW = W - 2 * X0, TOP = 1.45, BOTTOM = 6.65;

// The frame: block title, subject line, source line. No footer, logo or slide number, so a block pastes cleanly.
pres.defineSlideMaster({
  title: "RADIX_BLOCK",
  background: { color: "FFFFFF" },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.4, w: CW, h: 0.6, fontFace: FONT, fontSize: 24, bold: true, color: STRONG, align: "left", valign: "top", margin: 0 }, text: "" } },
  ],
});
const T = (s, text, o) => s.addText(text, Object.assign({ fontFace: FONT, color: INK, margin: 0, isTextBox: true, valign: "top" }, o));
const block = (title, subject, source) => {
  const s = pres.addSlide({ masterName: "RADIX_BLOCK" });
  s.addText(title, { placeholder: "title", align: "left" });
  T(s, subject, { x: X0, y: 0.98, w: CW, h: 0.3, fontSize: 12, color: FAINT, objectName: "Subject" });
  T(s, source, { x: X0, y: 6.8, w: CW, h: 0.4, fontSize: 10, color: FAINT, objectName: "Source" });
  return s;
};
const subject = (...parts) => [deal.name].concat(parts).filter(Boolean).join(" · ");

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
const evenCols = (w, first, n) => [first].concat(Array(n).fill((w - first) / n));
const chartBase = (title) => ({
  fontFace: FONT, catAxisLabelFontFace: FONT, valAxisLabelFontFace: FONT, dataLabelFontFace: FONT, legendFontFace: FONT, titleFontFace: FONT,
  catAxisLabelColor: FAINT, valAxisLabelColor: FAINT, catAxisLabelFontSize: 10, valAxisLabelFontSize: 9,
  valGridLine: { color: RULE, size: 0.5 }, catGridLine: { style: "none" }, catAxisLineShow: true, catAxisLineColor: "D5D7DA",
  dataLabelColor: MUTED, dataLabelFontSize: 9, legendColor: MUTED, legendFontSize: 10,
  showTitle: true, title, titleFontSize: 12, titleColor: STRONG,
});

const draw = {
  // Key facts as tiles. Data only: no adjectives, no drafted copy.
  property_snapshot() {
    const s = block("Property snapshot", subject(deal.address, `Rent roll as of ${rrDate}`), `Radix deal record and rent roll as of ${rrDate}. Contractual rent.`);
    const tiles = [
      ["Units", int(units)], ["Year built", deal.year_built ? String(deal.year_built) : "-"],
      ["Average unit size", isNum((um.total || {}).avg_sf) ? `${int(um.total.avg_sf)} SF` : "-"], ["Occupancy", pct(snap.occupancy_pct)],
      ["Vacant units", int(snap.vacant_units)], ["Average market rent", money(snap.market_rent)],
      ["Average in-place rent", money(snap.in_place_rent)], ["In-place as % of market", pct(snap.pct_of_market)],
    ];
    const gap = 0.25, tw = (CW - 3 * gap) / 4, th = 2.3;
    tiles.forEach(([label, val], i) => {
      const x = X0 + (i % 4) * (tw + gap), y = TOP + 0.1 + Math.floor(i / 4) * (th + gap);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: tw, h: th, rectRadius: 0.08, fill: { color: i < 4 ? "FFFFFF" : "FFFFFF" }, line: { color: RULE, width: 0.75 } });
      T(s, label, { x: x + 0.3, y: y + 0.35, w: tw - 0.6, h: 0.35, fontSize: 13, color: MUTED });
      T(s, val, { x: x + 0.3, y: y + 0.9, w: tw - 0.6, h: 0.8, fontSize: 32, bold: true, color: PRIMARY });
    });
  },

  unit_mix() {
    const s = block("Unit mix", subject(`Rent roll as of ${rrDate}`), `Radix rent roll as of ${rrDate}. Contractual rent. Market rent per SF derived.`);
    const rows = um.rows.map((r) => ({ cells: [unitType(r), int(r.units), pct(100 * r.units / units), int(r.avg_sf), money(r.market_rent),
      money(r.in_place_rent), isNum(r.market_rent) && r.avg_sf ? `$${(r.market_rent / r.avg_sf).toFixed(2)}` : "-", pct(r.occupied_pct)] }));
    const t = um.total;
    rows.push({ bold: true, fill: CANVAS, cells: ["Total / avg", int(t.units), "100.0%", int(t.avg_sf), money(t.market_rent), money(t.in_place_rent), `$${(t.market_rent / t.avg_sf).toFixed(2)}`, pct(t.occupied_pct)] });
    const rowH = 0.4;
    table(s, ["Unit type", "Units", "% of units", "Avg SF", "Market rent", "In-place rent", "Market $/SF", "Occupied"], rows,
      { x: X0, y: TOP, w: CW, colW: evenCols(CW, 2.6, 7), fontSize: 12, rowH });
    const bottom = TOP + rowH * (rows.length + 1);
    if (BOTTOM - bottom > 1.6) s.addChart(pres.charts.BAR, [{ name: "Units", labels: um.rows.map(unitType), values: um.rows.map((r) => r.units) }],
      Object.assign(chartBase("Units by unit type"), { x: X0, y: bottom + 0.3, w: CW, h: BOTTOM - bottom - 0.3, barDir: "bar", barGapWidthPct: 45, catAxisOrientation: "maxMin",
        chartColors: [PRIMARY], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "#,##0", showLegend: false, valAxisHidden: true, valGridLine: { style: "none" } }));
  },

  rents_vs_market() {
    const s = block("Rents vs. market", subject(`Rent roll as of ${rrDate}`),
      `Radix rent roll as of ${rrDate}. Contractual rent. % of market: in-place rent as a share of market rent. Last 90 days: average rent on leases signed in the 90 days before the rent roll date.`);
    const labels = um.rows.map(unitType);
    s.addChart(pres.charts.BAR, [
      { name: "Market rent", labels, values: um.rows.map((r) => Math.round(r.market_rent)) },
      { name: "In-place rent", labels, values: um.rows.map((r) => Math.round(r.in_place_rent)) },
      { name: "Leases, last 90 days", labels, values: um.rows.map((r) => Math.round(r.last90_rent || 0)) },
    ], Object.assign(chartBase("Average rent per unit per month"), {
      x: X0, y: TOP, w: 6.6, h: BOTTOM - TOP, barDir: "col", barGapWidthPct: 60, chartColors: [PRIMARY, ACCENT, HUSH],
      showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "$#,##0", valAxisLabelFormatCode: "$#,##0", showLegend: true, legendPos: "b",
    }));
    const rows = um.rows.map((r) => ({ cells: [unitType(r), int(r.units), money(r.market_rent), money(r.in_place_rent), pct(r.pct_of_market), isNum(r.last90_rent) ? money(r.last90_rent) : "-"] }));
    const t = um.total;
    rows.push({ bold: true, fill: CANVAS, cells: ["Total / avg", int(t.units), money(t.market_rent), money(t.in_place_rent), pct(t.pct_of_market), money(t.last90_rent)] });
    const x = 7.45, w = W - X0 - x;
    table(s, ["Unit type", "Units", "Market", "In-place", "% of market", "Last 90 days"], rows, { x, y: TOP, w, colW: [1.4, 0.6, 0.8, 0.8, 0.9, w - 4.5], fontSize: 10, rowH: 0.38 });
  },

  operating_history() {
    const s = block("Operating history", subject(`T12 ${cols[0] ? cols[0].window : ""}`), "Radix operating statement, actuals. T3 and T1 are annualized.");
    const labels = (m.months || []).map(ym);
    s.addChart(pres.charts.LINE, [
      { name: "Effective gross revenue", labels, values: m.egr.map(Math.round) },
      { name: "Operating expenses", labels, values: m.opex.map(Math.round) },
      { name: "Net operating income", labels, values: m.noi.map(Math.round) },
    ], Object.assign(chartBase("By month"), {
      x: X0, y: TOP, w: 7.1, h: BOTTOM - TOP, chartColors: [ACCENT, HUSH, PRIMARY], lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 5,
      valAxisLabelFormatCode: "$#,##0", showLegend: true, legendPos: "b",
    }));
    const rows = [["egr", "Effective gross revenue"], ["opex", "Operating expenses"], ["noi", "Net operating income"]]
      .map(([k, l]) => ({ bold: k === "noi", fill: k === "noi" ? TINT : undefined, cells: [l].concat(cols.map((c) => money((act[k] || {})[c.key]))) }));
    rows.push({ muted: true, cells: ["NOI per unit"].concat(cols.map((c) => money((act.noi || {})[c.key] / units))) });
    const x = 8.0, w = W - X0 - x;
    table(s, ["$ annual"].concat(cols.map((c) => c.label)), rows, { x, y: TOP, w, colW: evenCols(w, 2.0, cols.length), fontSize: 10, rowH: 0.4 });
    T(s, cols.map((c) => `${c.label}: ${c.window}`).join("\n"), { x, y: TOP + 0.4 * (rows.length + 1) + 0.2, w, h: 0.9, fontSize: 10, color: FAINT });
  },

  // Actuals by group; with the client's model, the Year 1 pro forma next to them.
  operating_statement() {
    const title = pf ? "Actuals to pro forma" : "Operating statement";
    const s = block(title, subject(cols.map((c) => `${c.label} ${c.window}`).join(" · ")),
      `Actuals from the Radix operating statement.${pf ? ` Pro forma from ${modelFile}.` : ""} Groups${pf ? ", per-unit figures and changes" : " and per-unit figures"} derived.`);
    const header = ["$ annual"].concat(cols.map((c) => c.label)).concat(pf ? [pf.label || "Year 1 pro forma", "Per unit", "Change vs T12"] : ["T12 per unit"]);
    const mk = (key, label, opt = {}) => {
      const cells = [label].concat(cols.map((c) => money(actualOf(key, c.key))));
      if (pf) {
        const p = pfOf(key), a = actualOf(key, "T12");
        cells.push(money(p), isNum(p) && units ? money(p / units) : "-", signedCompact(isNum(p) && isNum(a) ? p - a : null));
      } else {
        const a = actualOf(key, "T12");
        cells.push(isNum(a) && units ? money(a / units) : "-");
      }
      return Object.assign({ cells }, opt);
    };
    const sec = (t) => ({ bold: true, muted: true, fill: CANVAS, cells: [t].concat(Array(header.length - 1).fill("")) });
    const rows = [sec("Revenue")].concat(REV.map(([k, l]) => mk(k, l)), [mk("egr", "Effective gross revenue", { bold: true }), sec("Operating expenses")],
      EXP.map(([k, l]) => mk(k, l)), [mk("opex", "Total operating expenses", { bold: true }), mk("noi", "Net operating income", { bold: true, fill: TINT })]);
    table(s, header, rows, { x: X0, y: TOP, w: CW, colW: evenCols(CW, 3.0, header.length - 1), fontSize: 11, rowH: 0.34 });
  },

  proforma_cash_flow() {
    const years = hcf.years || hcf.noi.map((_, i) => `Year ${i + 1}`);
    const s = block("Pro forma cash flow", subject(`${years.length}-year hold`), `From ${modelFile || "the client model"}.`);
    s.addChart(pres.charts.BAR, [{ name: "Net operating income", labels: years, values: hcf.noi.map(Math.round) }], Object.assign(chartBase("Net operating income by year"), {
      x: X0, y: TOP, w: CW, h: 2.9, barDir: "col", barGapWidthPct: 70, chartColors: [PRIMARY], showValue: true, dataLabelPosition: "outEnd", valAxisMinVal: 0,
      dataLabelFormatCode: "$#,##0", valAxisLabelFormatCode: "$#,##0", showLegend: false,
    }));
    const rows = [["egr", "Effective gross revenue"], ["opex", "Operating expenses"], ["noi", "Net operating income"]].filter(([k]) => hcf[k])
      .map(([k, l]) => ({ bold: k === "noi", fill: k === "noi" ? TINT : undefined, cells: [l].concat(hcf[k].map((v) => money(v))) }));
    table(s, ["$"].concat(years), rows, { x: X0, y: 4.6, w: CW, colW: evenCols(CW, 2.6, years.length), fontSize: 11, rowH: 0.38 });
  },

  proforma_assumptions() {
    const s = block("Pro forma assumptions", subject(), `From ${modelFile || "the client model"}, as the model states them.`);
    const list = data.assumptions;
    const half = Math.ceil(list.length / 2), colw = (CW - 0.6) / 2;
    list.forEach((a, i) => {
      const x = X0 + (i < half ? 0 : colw + 0.6), y = TOP + (i % half) * 0.68;
      T(s, a.label, { x, y, w: colw * 0.38, h: 0.45, fontSize: 14, color: FAINT });
      T(s, a.value, { x: x + colw * 0.38, y, w: colw * 0.62, h: 0.45, fontSize: 14, bold: true, color: INK, align: "right" });
      s.addShape(pres.shapes.LINE, { x, y: y + 0.55, w: colw, h: 0, line: { color: RULE, width: 0.75 } });
    });
  },

  rent_comps() {
    const s = block("Rent comparables", subject(`${comps.deals.length} comparable propert${comps.deals.length === 1 ? "y" : "ies"} in Radix`), comps.source || "Radix rent comp set. Contractual rent.");
    const subj = {}; for (const r of um.rows || []) subj[typeKey(r)] = r;
    const deals = comps.deals;
    const all = {}; for (const r of (um.rows || []).concat(...deals.map((d) => d.rows))) all[typeKey(r)] = r;
    const present = Object.keys(all).sort((a, b) => all[a].beds - all[b].beds || all[a].baths - all[b].baths);
    // Chart only the unit types every property has, so no bar is a missing value drawn as $0.
    const chartKeys = present.filter((k) => subj[k] && deals.every((d) => d.rows.some((r) => typeKey(r) === k)));
    const chartLabels = chartKeys.map((k) => unitType(all[k]));
    s.addChart(pres.charts.BAR, [{ name: `${deal.name} (subject)`, labels: chartLabels, values: chartKeys.map((k) => Math.round(subj[k].in_place_rent)) }]
      .concat(deals.map((d) => ({ name: d.name, labels: chartLabels, values: chartKeys.map((k) => Math.round(d.rows.find((x) => typeKey(x) === k).in_place_rent)) }))),
      Object.assign(chartBase("Average in-place rent by unit type"), { x: X0, y: TOP, w: 5.2, h: BOTTOM - TOP, barDir: "col", barGapWidthPct: 60, chartColors: [PRIMARY, HUSH, ACCENT, "D5D7DA", "717680", "BACFF9"],
        showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "$#,##0", valAxisLabelFormatCode: "$#,##0", showLegend: true, legendPos: "b" }));
    const rows = [];
    const addProp = (name, asOf, rowsBy, total, fill) => {
      rows.push({ bold: true, fill: fill || CANVAS, cells: [`${name} · as of ${asOf}`, "", "", "", "", ""] });
      for (const k of present) {
        const r = rowsBy[k]; if (!r) continue;
        rows.push({ cells: [`   ${unitType(r)}`, int(r.units), int(r.avg_sf), money(r.market_rent), money(r.in_place_rent), pct(r.occupied_pct)] });
      }
      if (total) rows.push({ bold: true, cells: ["   Total / avg", int(total.units), int(total.avg_sf), money(total.market_rent), money(total.in_place_rent), pct(total.occupied_pct)] });
    };
    addProp(`${deal.name} (subject)`, rrDate, subj, um.total, TINT);
    for (const d of deals) { const by = {}; for (const r of d.rows) by[typeKey(r)] = r; addProp(`${d.name}, ${d.city}`, dateLabel(d.as_of), by, d.total); }
    const x = 6.0, w = W - X0 - x;
    const rowH = Math.min(0.3, (BOTTOM - TOP) / (rows.length + 1));
    table(s, ["Property / unit type", "Units", "Avg SF", "Market", "In-place", "Occupied"], rows, { x, y: TOP, w, colW: [3.05, 0.65, 0.7, 0.8, 0.8, w - 6.0], fontSize: rowH < 0.3 ? 9 : 10, rowH });
  },
};

for (const b of rendered) draw[b]();

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
      ["", "## Checks"], checks.map((c) => `- ${c.ok ? "PASS" : "FAIL"}: ${c.check}${!c.ok && c.detail ? ` (${c.detail})` : ""}`),
      ["", "## Files"], outputs.map((o) => `- ${o}`), pngNote ? [`- ${pngNote}`] : []).join("\n");
  fs.writeFileSync(path.join(outDir, `${stem}-run-summary.md`), summary + "\n");
  console.log(JSON.stringify({ status, rendered, skipped, outputs, png_note: pngNote, failed }, null, 2));
});
