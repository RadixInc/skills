/*
 * Shared Radix data block library. The deal-data-blocks skill and the offering-memorandum skill
 * draw every block with this one file, so a block looks the same whether it lands in a user's own
 * document or in a Radix-built OM, and a fix to a block reaches both.
 *
 * THE COPIES MUST STAY IDENTICAL. deal-data-blocks/scripts/blocks_lib.js is the source;
 * offering-memorandum/scripts/blocks_lib.js is a copy (each skill ships on its own).
 * Edit the source, then copy it over. scripts/validate_skills.py fails when they differ.
 *
 *   const createBlocks = require("./blocks_lib");
 *   const B = createBlocks({ pres, data, brand, frame });
 *   const { rendered, skipped } = B.plan(ids);  // drops blocks without their data
 *   B.gate(rendered);                           // accuracy checks land in B.checks
 *   rendered.forEach((id) => B.draw[id]());
 *
 * `frame` (optional) lets a document add its own chrome to block slides: { master, decorate(slide, id) }.
 * Without it, a block slide has no footer, logo or page number, so it pastes cleanly.
 */
"use strict";

// The catalog, in display order. Block ids are stable: users and saved defaults refer to them.
const CATALOG = ["property_snapshot", "unit_mix", "rents_vs_market", "operating_history", "operating_statement", "proforma_cash_flow", "proforma_assumptions", "rent_comps"];
const BLOCK_TITLES = { property_snapshot: "Property snapshot", unit_mix: "Unit mix", rents_vs_market: "Rents vs. market", operating_history: "Operating history",
  operating_statement: "Operating statement", proforma_cash_flow: "Pro forma cash flow", proforma_assumptions: "Pro forma assumptions", rent_comps: "Rent comparables" };

function createBlocks({ pres, data, brand, frame }) {
  // Every string a block prints is kept here, so a document can check that drafted text only cites printed figures.
  const shown = [];
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

  // ---------- brand (colors only; layout, type scale and neutrals are fixed) ----------
  const hex = (c, d) => (typeof c === "string" && /^#[0-9a-fA-F]{6}$/.test(c) ? c.slice(1).toUpperCase() : d);
  const colors = brand.colors || {};
  // Contrast guard: a brand color can't make figures hard to read. Primary and accent must reach 3:1 on white
  // (darkened in small steps until they do); the tint must stay light (lightened toward white until it does).
  const colorNotes = [];
  const rgb = (h) => [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  const toHex = (c) => c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("").toUpperCase();
  const lum = (h) => { const [r, g, b] = rgb(h).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const onWhite = (h) => 1.05 / (lum(h) + 0.05);
  const mix = (h, t, f) => toHex(rgb(h).map((v, i) => v + (rgb(t)[i] - v) * f));
  function guard(h, role, kind) {
    let c = h, n = 0;
    if (kind === "dark") while (onWhite(c) < 3 && n < 40) { c = mix(c, "000000", 0.05); n++; }
    else while (onWhite(c) > 1.15 && n < 40) { c = mix(c, "FFFFFF", 0.1); n++; }
    if (c !== h) colorNotes.push(`${role} #${h} adjusted to #${c} so figures stay readable.`);
    return c;
  }
  const PRIMARY = guard(hex(colors.primary, "144A85"), "Primary", "dark"), ACCENT = guard(hex(colors.accent, "1F76D6"), "Accent", "dark"), TINT = guard(hex(colors.accent_tint, "EFF4FE"), "Accent tint", "light");
  // Warm neutrals: an off-white page, white cards, hairline rules.
  const INK = "141414", STRONG = "1C1C1E", MUTED = "4A4A4F", FAINT = "85858A", HUSH = "C9C7C1", RULE = "E6E3DC", CANVAS = "F7F6F2", PAGE = "FBFAF7";
  // Blocks are pasted into the user's own files, so use a font every Office install has.
  const DECK_SAFE = ["Arial", "Calibri", "Cambria", "Georgia"];
  const FONT = DECK_SAFE.includes((brand.fonts || {}).body) ? brand.fonts.body : "Arial";
  // Headlines and headline numbers use a serif display face; Georgia ships with every Office install.
  const DISPLAY = DECK_SAFE.includes((brand.fonts || {}).heading) ? brand.fonts.heading : "Georgia";

  // ---------- data ----------
  const deal = data.deal || {}, src = data.sources || {}, act = data.actuals || {}, pf = data.proforma || null;
  const snap = data.snapshot || {}, units = deal.units;
  // Operating statement rows: the line breakdown multifamily OMs use. Every actual line and every pro forma figure maps to one.
  const REV = [["gross_potential_rent", "Gross potential rent"], ["loss_to_lease", "Loss to lease"], ["vacancy", "Vacancy"], ["concessions", "Concessions"],
    ["credit_loss", "Bad debt and non-revenue units"], ["other_income", "Other income"]];
  const EXP = [["payroll", "Payroll"], ["repairs_maintenance", "Repairs, maintenance and turnover"], ["contract_services", "Contract services and landscaping"],
    ["marketing", "Marketing and leasing"], ["administrative", "General and administrative"], ["utilities", "Utilities"],
    ["real_estate_taxes", "Real estate taxes"], ["insurance", "Insurance"], ["management", "Management fee"]];
  const CATS = REV.concat(EXP).map(([k]) => k);
  const cols = act.columns || [];
  const lines = (act.revenue || []).concat(act.expenses || []);
  const groupSum = (g, k) => { const vs = lines.filter((l) => l.category === g).map((l) => l.values[k]).filter(isNum); return vs.length ? vs.reduce((a, b) => a + b, 0) : null; };
  const groups = {}; for (const [g] of REV.concat(EXP)) { groups[g] = {}; for (const c of cols) groups[g][c.key] = groupSum(g, c.key); }
  const actualOf = (key, col) => (["egr", "opex", "noi"].includes(key) ? (act[key] || {})[col] : groups[key][col]);
  const pfOf = (key) => (!pf ? null : ["egr", "opex", "noi"].includes(key) ? pf[key] : (pf.categories || {})[key]);
  // Unit mix is always by bed / bath (groupBy unitMixBath), never by floor plan.
  const um = data.unit_mix || {};
  const bathLabel = (b) => (Number.isInteger(b) ? String(b) : Number(b).toFixed(1));
  const unitType = (r) => `${r.beds === 0 ? "Studio" : `${r.beds} bed`} / ${bathLabel(r.baths)} bath`;
  const typeKey = (r) => `${r.beds}-${r.baths}`;
  const rrDate = dateLabel((src.rent_roll || {}).as_of);
  const modelFile = (src.client_model || {}).file;
  const hcf = data.hold_cash_flow || {};
  const hist = (data.history || {}).columns || [];
  const comps = data.comps;

  // What each block needs. A selected block without its data is skipped and reported, never drawn empty.
  const needs = {
    property_snapshot: () => (isNum(units) && isNum(snap.occupancy_pct) ? null : "deal units and rent roll occupancy"),
    unit_mix: () => ((um.rows || []).length ? null : "a mapped rent roll"),
    rents_vs_market: () => ((um.rows || []).length ? null : "a mapped rent roll"),
    operating_history: () => (hist.length && cols.length ? null : "more than 12 months of mapped operating statements"),
    operating_statement: () => (cols.length ? null : "a mapped T12"),
    proforma_cash_flow: () => ((hcf.noi || []).length ? null : "the client's model"),
    proforma_assumptions: () => ((data.assumptions || []).length ? null : "the client's model"),
    rent_comps: () => (comps && (comps.deals || []).length ? null : "comparable properties with recent rent rolls in Radix"),
  };
  function plan(ids) {
      const want = ids && ids.length ? ids : CATALOG;
      const unknown = want.filter((b) => !CATALOG.includes(b));
      if (unknown.length) throw new Error(`Unknown block ids: ${unknown.join(", ")}`);
      const skipped = [], rendered = [];
      for (const b of CATALOG.filter((x) => want.includes(x))) { const n = needs[b](); if (n) skipped.push({ block: b, needs: n }); else rendered.push(b); }
      return { rendered, skipped };
    }
  // ---------- accuracy gate (only for the data the rendered blocks use) ----------
  const checks = [];
  const check = (name, ok, detail = "") => checks.push({ check: name, ok: !!ok, detail });
  const TOL = 1;
  function gate(rendered) {
    const uses = (...b) => b.some((x) => rendered.includes(x));
    if (uses("operating_history", "operating_statement")) {
      for (const h of hist) check(`History ${h.label}: NOI = EGR - OpEx and its months are stated`, Math.abs(h.egr - h.opex - h.noi) <= TOL && !!h.window);
      for (const c of cols) {
        const k = c.key;
        const rev = (act.revenue || []).reduce((a, r) => a + (r.values[k] || 0), 0);
        const exp = (act.expenses || []).reduce((a, r) => a + (r.values[k] || 0), 0);
        const egr = (act.egr || {})[k], opex = (act.opex || {})[k], noi = (act.noi || {})[k];
        if (isNum(egr)) check(`Actual ${k}: revenue lines sum to EGR`, Math.abs(rev - egr) <= TOL, `${rev.toFixed(2)} vs ${egr}`);
        if (isNum(opex)) check(`Actual ${k}: expense lines sum to OpEx`, Math.abs(exp - opex) <= TOL, `${exp.toFixed(2)} vs ${opex}`);
        if ([egr, opex, noi].every(isNum)) check(`Actual ${k}: NOI = EGR - OpEx`, Math.abs(egr - opex - noi) <= TOL);
      }
      check("Every actual line has a known category", lines.every((l) => CATS.includes(l.category)), lines.filter((l) => !CATS.includes(l.category)).map((l) => l.label).join(", "));
      check("Actual column windows are stated", cols.every((c) => c.window));
    }
    if (uses("operating_statement", "proforma_cash_flow") && pf) {
      const g = pf.categories || {};
      const r = REV.reduce((a, [k]) => a + (g[k] || 0), 0), e = EXP.reduce((a, [k]) => a + (g[k] || 0), 0);
      check("Pro forma: every category is filled", CATS.every((k) => isNum(g[k])), CATS.filter((k) => !isNum(g[k])).join(", "));
      check("Pro forma: revenue categories sum to EGR", Math.abs(r - pf.egr) <= TOL, `${r} vs ${pf.egr}`);
      check("Pro forma: expense categories sum to OpEx", Math.abs(e - pf.opex) <= TOL, `${e} vs ${pf.opex}`);
      check("Pro forma: NOI = EGR - OpEx", Math.abs(pf.egr - pf.opex - pf.noi) <= TOL);
      if ((hcf.noi || []).length) check("Pro forma Y1 NOI matches the cash flow's Y1", Math.abs(hcf.noi[0] - pf.noi) <= TOL);
    }
    if (uses("proforma_cash_flow")) {
      const rv = hcf.revenue || {};
      if (Object.keys(rv).length) hcf.egr.forEach((e, i) => check(`Cash flow ${hcf.years[i]}: revenue lines sum to EGR`, Math.abs(REV.reduce((a, [k]) => a + ((rv[k] || [])[i] || 0), 0) - e) <= TOL));
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
    return checks;
  }
  const W = 13.333, X0 = 0.6, CW = W - 2 * X0, TOP = 1.6, BOTTOM = 6.6;

  // The frame: block title, subject line, source line. No footer, logo or slide number, so a block pastes cleanly.
  if (!pres._radixBlockMaster) { pres._radixBlockMaster = true; pres.defineSlideMaster({
    title: "RADIX_BLOCK",
    background: { color: PAGE },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.68, w: CW, h: 0.7, fontFace: DISPLAY, fontSize: 30, bold: false, color: INK, align: "left", valign: "top", margin: 0 }, text: "" } },
    ],
  }); }
  const T = (s, text, o) => { (Array.isArray(text) ? text.map((t) => t.text) : [text]).forEach((t) => shown.push(String(t))); return s.addText(text, Object.assign({ fontFace: FONT, color: INK, margin: 0, isTextBox: true, valign: "top" }, o)); };
  let current = null;
  const block = (title, subject, source) => {
    const s = pres.addSlide({ masterName: (frame && frame.master) || "RADIX_BLOCK", sectionTitle: frame && frame.section ? frame.section(current) : undefined });
    shown.push(title);
    s.addText(title, { placeholder: "title", align: "left" });
    // Eyebrow: the deal and the data's date, small caps above the title.
    T(s, String(subject || "").toUpperCase(), { x: X0, y: 0.38, w: CW, h: 0.25, fontSize: 9, bold: true, color: FAINT, charSpacing: 1.5, objectName: "Subject" });
    T(s, source, { x: X0, y: 6.78, w: frame && frame.sourceWidth ? frame.sourceWidth : CW, h: 0.35, fontSize: 8.5, color: FAINT, objectName: "Source" });
    if (frame && frame.decorate) frame.decorate(s, current);
    return s;
  };
  const subject = (...parts) => [deal.name].concat(parts).filter(Boolean).join(" · ");

  // Tables: horizontal hairlines only, no fills except a soft tint on the key row, a ruled total line.
  function table(s, header, rows, o) {
    const fs_ = o.fontSize || 11;
    header.forEach((h) => shown.push(String(h))); rows.forEach((r) => r.cells.forEach((c) => shown.push(String(c))));
    const NONE = { type: "none" };
    const line = (pt, color) => ({ type: "solid", pt, color });
    const head = header.map((h, i) => ({ text: String(h).toUpperCase(), options: { bold: true, color: FAINT, align: i ? "right" : "left", fontSize: Math.max(7.5, fs_ - 2.5), charSpacing: 0.5,
      border: [NONE, NONE, line(0.75, STRONG), NONE] } }));
    const body = rows.map((r, ri) => {
      const section = r.bold && r.muted, total = !section && r.fill === CANVAS, key = r.fill === TINT;
      const top = total ? line(0.75, STRONG) : NONE;
      const bottom = ri === rows.length - 1 ? NONE : line(0.5, RULE);
      return r.cells.map((c, i) => ({
        text: section ? String(c).toUpperCase() : c,
        options: { align: i ? "right" : "left", bold: !!r.bold && !section, color: section ? FAINT : r.muted ? FAINT : INK, fontSize: section ? Math.max(7.5, fs_ - 2.5) : fs_,
          charSpacing: section ? 0.5 : 0, fill: key ? { color: TINT } : undefined, border: [top, NONE, bottom, NONE] },
      }));
    });
    s.addTable([head].concat(body), {
      x: o.x, y: o.y, w: o.w, colW: o.colW, fontFace: FONT, fontSize: fs_, color: INK, valign: "middle",
      rowH: o.rowH || 0.3, margin: [0.03, 0.08, 0.03, 0.08], autoPage: false,
    });
  }
  // A white card with a hairline border, the surface every chart and tile sits on.
  const card = (s, x, y, w, h) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: "FFFFFF" }, line: { color: RULE, width: 0.75 } });
  // Charts sit inside a card, inset from its edge.
  const chartCard = (s, type, series, o) => {
    card(s, o.x, o.y, o.w, o.h);
    return s.addChart(type, series, Object.assign({}, o, { x: o.x + 0.2, y: o.y + 0.15, w: o.w - 0.4, h: o.h - 0.3 }));
  };
  const evenCols = (w, first, n) => [first].concat(Array(n).fill((w - first) / n));
  const chartBase = (title) => ({
    fontFace: FONT, catAxisLabelFontFace: FONT, valAxisLabelFontFace: FONT, dataLabelFontFace: FONT, legendFontFace: FONT, titleFontFace: FONT,
    catAxisLabelColor: FAINT, valAxisLabelColor: FAINT, catAxisLabelFontSize: 9, valAxisLabelFontSize: 8,
    valGridLine: { color: RULE, size: 0.5, style: "dash" }, catGridLine: { style: "none" }, catAxisLineShow: false, valAxisLineShow: false,
    dataLabelColor: MUTED, dataLabelFontSize: 8, legendColor: MUTED, legendFontSize: 9, legendPos: "t",
    showTitle: !!title, title, titleFontSize: 10, titleColor: FAINT, titleFontFace: FONT,
  });

  const drawFns = {
    // Key facts as tiles. Data only: no adjectives, no drafted copy.
    property_snapshot() {
      const s = block("Property snapshot", subject(deal.address, `Rent roll as of ${rrDate}`), `Radix deal record and rent roll as of ${rrDate}. Contractual rent.`);
      const tiles = [
        ["Units", int(units)], ["Year built", deal.year_built ? String(deal.year_built) : "-"],
        ["Rentable SF", isNum(deal.total_sf) ? int(deal.total_sf) : "-"], ["Average unit size", isNum((um.total || {}).avg_sf) ? `${int(um.total.avg_sf)} SF` : "-"],
        ["Occupancy", pct(snap.occupancy_pct)], ["Average market rent", money(snap.market_rent)],
        ["Average in-place rent", money(snap.in_place_rent)], ["In-place as % of market", pct(snap.pct_of_market)],
      ];
      const gap = 0.2, tw = (CW - 3 * gap) / 4, th = 2.2;
      tiles.forEach(([label, val], i) => {
        const x = X0 + (i % 4) * (tw + gap), y = TOP + 0.1 + Math.floor(i / 4) * (th + gap);
        card(s, x, y, tw, th);
        T(s, val, { x: x + 0.3, y: y + 0.3, w: tw - 0.6, h: 0.95, fontSize: 40, fontFace: DISPLAY, color: INK, valign: "bottom" });
        s.addShape(pres.shapes.LINE, { x: x + 0.3, y: y + th - 0.75, w: 0.35, h: 0, line: { color: ACCENT, width: 1.5 } });
        T(s, label, { x: x + 0.3, y: y + th - 0.6, w: tw - 0.6, h: 0.35, fontSize: 11, color: MUTED });
      });
    },

    unit_mix() {
      const s = block("Unit mix", subject(`Rent roll as of ${rrDate}`), `Radix rent roll as of ${rrDate}. Contractual rent. Rent per SF and % of units derived.`);
      const psf = (rent, sf) => (isNum(rent) && sf ? `$${(rent / sf).toFixed(2)}` : "-");
      const rows = um.rows.map((r) => ({ cells: [unitType(r), int(r.units), pct(100 * r.units / units), int(r.avg_sf), money(r.market_rent), psf(r.market_rent, r.avg_sf),
        money(r.in_place_rent), psf(r.in_place_rent, r.avg_sf), pct(r.occupied_pct)] }));
      const t = um.total;
      rows.push({ bold: true, fill: CANVAS, cells: ["Total / avg", int(t.units), "100.0%", int(t.avg_sf), money(t.market_rent), psf(t.market_rent, t.avg_sf), money(t.in_place_rent), psf(t.in_place_rent, t.avg_sf), pct(t.occupied_pct)] });
      const rowH = 0.4;
      table(s, ["Unit type", "Units", "% of units", "Avg SF", "Market rent", "Market $/SF", "In-place rent", "In-place $/SF", "Occupied"], rows,
        { x: X0, y: TOP, w: CW, colW: evenCols(CW, 2.4, 8), fontSize: 12, rowH });
      const bottom = TOP + rowH * (rows.length + 1);
      if (BOTTOM - bottom > 1.6) chartCard(s, pres.charts.BAR, [{ name: "Units", labels: um.rows.map(unitType), values: um.rows.map((r) => r.units) }],
        Object.assign(chartBase("Units by unit type"), { x: X0, y: bottom + 0.3, w: CW, h: BOTTOM - bottom - 0.3, barDir: "bar", barGapWidthPct: 70, catAxisOrientation: "maxMin",
          chartColors: [PRIMARY], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "#,##0", showLegend: false, valAxisHidden: true, valGridLine: { style: "none" } }));
    },

    // Where in-place rents sit against market, and what recent leases achieved.
    rents_vs_market() {
      const s = block("Rents vs. market", subject(`Rent roll as of ${rrDate}`),
        `Radix rent roll as of ${rrDate}. Contractual rent. Gap to market (market less in-place, per unit per month) derived. Last 90 days: average rent on leases signed in the 90 days before the rent roll date.`);
      const labels = um.rows.map(unitType);
      chartCard(s, pres.charts.BAR, [
        { name: "Market rent", labels, values: um.rows.map((r) => Math.round(r.market_rent)) },
        { name: "In-place rent", labels, values: um.rows.map((r) => Math.round(r.in_place_rent)) },
        { name: "Leases, last 90 days", labels, values: um.rows.map((r) => Math.round(r.last90_rent || 0)) },
      ], Object.assign(chartBase("Average rent per unit per month"), {
        x: X0, y: TOP, w: 6.2, h: BOTTOM - TOP, barDir: "col", barGapWidthPct: 90, chartColors: [HUSH, PRIMARY, ACCENT],
        showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "$#,##0", valAxisLabelFormatCode: "$#,##0", showLegend: true, legendPos: "b",
      }));
      const gap = (r) => (isNum(r.market_rent) && isNum(r.in_place_rent) ? money(r.market_rent - r.in_place_rent) : "-");
      const rows = um.rows.map((r) => ({ cells: [unitType(r), int(r.units), money(r.market_rent), money(r.in_place_rent), gap(r), pct(r.pct_of_market), isNum(r.last90_rent) ? money(r.last90_rent) : "-"] }));
      const t = um.total;
      rows.push({ bold: true, fill: CANVAS, cells: ["Total / avg", int(t.units), money(t.market_rent), money(t.in_place_rent), gap(t), pct(t.pct_of_market), money(t.last90_rent)] });
      const x = 7.0, w = W - X0 - x;
      table(s, ["Unit type", "Units", "Market", "In-place", "Gap to market", "% of market", "Last 90 days"], rows,
        { x, y: TOP, w, colW: [1.35, 0.55, 0.72, 0.72, 0.85, 0.8, w - 4.99], fontSize: 11, rowH: 0.55 });
    },

    // Historical operating summary: each period Radix holds, side by side, as OMs show it. No monthly noise.
    operating_history() {
      const periods = hist.map((h) => ({ label: h.label, window: h.window, egr: h.egr, opex: h.opex, noi: h.noi }))
        .concat(cols.filter((c) => c.key !== "T1").map((c) => ({ label: c.label, window: c.window, egr: (act.egr || {})[c.key], opex: (act.opex || {})[c.key], noi: (act.noi || {})[c.key] })));
      const s = block("Operating history", subject(`${periods.length} periods`), `Radix operating statements, actuals. Partial years and T3 are annualized. Per-unit figures and expense ratio derived.`);
      const per = (v) => (isNum(v) && units ? money(v / units) : "-");
      const rows = [
        { cells: ["Effective gross revenue"].concat(periods.map((p) => money(p.egr))) },
        { muted: true, cells: ["   Per unit"].concat(periods.map((p) => per(p.egr))) },
        { cells: ["Operating expenses"].concat(periods.map((p) => money(p.opex))) },
        { muted: true, cells: ["   Per unit"].concat(periods.map((p) => per(p.opex))) },
        { muted: true, cells: ["   Expense ratio"].concat(periods.map((p) => (isNum(p.opex) && p.egr ? pct(100 * p.opex / p.egr) : "-"))) },
        { bold: true, fill: TINT, cells: ["Net operating income"].concat(periods.map((p) => money(p.noi))) },
        { muted: true, cells: ["   Per unit"].concat(periods.map((p) => per(p.noi))) },
      ];
      const rowH = 0.36;
      table(s, ["$ annual"].concat(periods.map((p) => p.label)), rows, { x: X0, y: TOP, w: CW, colW: evenCols(CW, 3.0, periods.length), fontSize: 11, rowH });
      const y = TOP + rowH * (rows.length + 1) + 0.15;
      T(s, periods.map((p) => `${p.label}: ${p.window}`).join("   ·   "), { x: X0, y, w: CW, h: 0.3, fontSize: 10, color: FAINT });
      const cy = y + 0.45;
      if (BOTTOM - cy > 1.4) chartCard(s, pres.charts.BAR, [
        { name: "Effective gross revenue", labels: periods.map((p) => p.label), values: periods.map((p) => Math.round(p.egr)) },
        { name: "Operating expenses", labels: periods.map((p) => p.label), values: periods.map((p) => Math.round(p.opex)) },
        { name: "Net operating income", labels: periods.map((p) => p.label), values: periods.map((p) => Math.round(p.noi)) },
      ], Object.assign(chartBase(""), { showTitle: false, x: X0, y: cy, w: CW, h: BOTTOM - cy, barDir: "col", barGapWidthPct: 80, chartColors: [HUSH, "E9E7E1", PRIMARY],
        showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "$#,##0.00,,\"M\"", valAxisHidden: true, valGridLine: { style: "none" }, showLegend: true, legendPos: "r" }));
    },

    // Line breakdown OMs use; with the client's model, the Year 1 pro forma next to the actuals.
    operating_statement() {
      const title = pf ? "Actuals to pro forma" : "Operating statement";
      const acols = cols.filter((c) => c.key !== "T1");
      const s = block(title, subject(acols.map((c) => `${c.label} ${c.window}`).join(" · ")),
        `Actuals from the Radix operating statement; T3 is annualized.${pf ? ` Pro forma from ${modelFile}.` : ""} Line categories, per-unit figures${pf ? " and changes" : ""} derived.`);
      const t12 = acols.find((c) => c.key === "T12") ? "T12" : acols[0].key;
      const header = ["$ annual"].concat(acols.flatMap((c) => (c.key === t12 ? [c.label, "Per unit"] : [c.label])))
        .concat(pf ? [pf.label || "Year 1 pro forma", "Per unit", `Change vs ${t12}`] : []);
      const per = (v) => (isNum(v) && units ? money(v / units) : "-");
      const mk = (key, label, opt = {}) => {
        const cells = [label].concat(acols.flatMap((c) => { const v = actualOf(key, c.key); return c.key === t12 ? [money(v), per(v)] : [money(v)]; }));
        if (pf) { const p = pfOf(key), a = actualOf(key, t12); cells.push(money(p), per(p), signedCompact(isNum(p) && isNum(a) ? p - a : null)); }
        return Object.assign({ cells }, opt);
      };
      const sec = (t) => ({ bold: true, muted: true, fill: CANVAS, cells: [t].concat(Array(header.length - 1).fill("")) });
      const rows = [sec("Revenue")].concat(REV.map(([k, l]) => mk(k, l)), [mk("egr", "Effective gross revenue", { bold: true }), sec("Operating expenses")],
        EXP.map(([k, l]) => mk(k, l)), [mk("opex", "Total operating expenses", { bold: true }), mk("noi", "Net operating income", { bold: true, fill: TINT })]);
      const rowH = Math.min(0.3, (BOTTOM - TOP) / (rows.length + 1));
      table(s, header, rows, { x: X0, y: TOP, w: CW, colW: evenCols(CW, 3.1, header.length - 1), fontSize: 10, rowH });
    },

    proforma_cash_flow() {
      const years = hcf.years || hcf.noi.map((_, i) => `Year ${i + 1}`);
      const s = block("Pro forma cash flow", subject(`${years.length}-year hold`), `From ${modelFile || "the client model"}. NOI per unit and growth derived.`);
      const rv = hcf.revenue || {};
      const rows = [];
      for (const [k, l] of REV) if (rv[k]) rows.push({ cells: [l].concat(rv[k].map((v) => money(v))) });
      rows.push({ bold: true, cells: ["Effective gross revenue"].concat(hcf.egr.map((v) => money(v))) });
      rows.push({ cells: ["Operating expenses"].concat(hcf.opex.map((v) => money(-v))) });
      rows.push({ bold: true, fill: TINT, cells: ["Net operating income"].concat(hcf.noi.map((v) => money(v))) });
      rows.push({ muted: true, cells: ["   Per unit"].concat(hcf.noi.map((v) => (units ? money(v / units) : "-"))) });
      rows.push({ muted: true, cells: ["   Growth"].concat(hcf.noi.map((v, i) => (i && hcf.noi[i - 1] ? pct(100 * (v / hcf.noi[i - 1] - 1)) : "-"))) });
      const rowH = 0.34;
      table(s, ["$"].concat(years), rows, { x: X0, y: TOP, w: CW, colW: evenCols(CW, 2.8, years.length), fontSize: 10, rowH });
      const cy = TOP + rowH * (rows.length + 1) + 0.25;
      if (BOTTOM - cy > 1.3) chartCard(s, pres.charts.BAR, [{ name: "Net operating income", labels: years, values: hcf.noi.map(Math.round) }], Object.assign(chartBase("Net operating income by year"), {
        x: X0, y: cy, w: CW, h: BOTTOM - cy, barDir: "col", barGapWidthPct: 110, chartColors: [PRIMARY], showValue: true, dataLabelPosition: "outEnd", valAxisMinVal: 0,
        dataLabelFormatCode: "$#,##0", valAxisHidden: true, valGridLine: { style: "none" }, showLegend: false,
      }));
    },

    proforma_assumptions() {
      const s = block("Pro forma assumptions", subject(), `From ${modelFile || "the client model"}, as the model states them.`);
      const list = data.assumptions;
      const half = Math.ceil(list.length / 2), colw = (CW - 1.4) / 2;
      card(s, X0, TOP, CW, Math.min(BOTTOM - TOP, half * 0.68 + 0.5));
      list.forEach((a, i) => {
        const x = X0 + 0.4 + (i < half ? 0 : colw + 0.6), y = TOP + 0.3 + (i % half) * 0.68;
        T(s, a.label, { x, y, w: colw * 0.38, h: 0.45, fontSize: 14, color: FAINT });
        T(s, a.value, { x: x + colw * 0.38, y: y - 0.06, w: colw * 0.62, h: 0.5, fontSize: 18, fontFace: DISPLAY, color: INK, align: "right" });
        if (i % half !== half - 1 && i !== list.length - 1) s.addShape(pres.shapes.LINE, { x, y: y + 0.55, w: colw, h: 0, line: { color: RULE, width: 0.5 } });
      });
    },

    rent_comps() {
      const s = block("Rent comparables", subject(`${comps.deals.length} comparable propert${comps.deals.length === 1 ? "y" : "ies"} in Radix`), `${comps.source || "Radix rent comp set."} Contractual rent. In-place rent per SF derived.`);
      const subj = {}; for (const r of um.rows || []) subj[typeKey(r)] = r;
      const deals = comps.deals;
      const all = {}; for (const r of (um.rows || []).concat(...deals.map((d) => d.rows))) all[typeKey(r)] = r;
      const present = Object.keys(all).sort((a, b) => all[a].beds - all[b].beds || all[a].baths - all[b].baths);
      // Chart only the unit types every property has, so no bar is a missing value drawn as $0.
      const chartKeys = present.filter((k) => subj[k] && deals.every((d) => d.rows.some((r) => typeKey(r) === k)));
      const chartLabels = chartKeys.map((k) => unitType(all[k]));
      chartCard(s, pres.charts.BAR, [{ name: `${deal.name} (subject)`, labels: chartLabels, values: chartKeys.map((k) => Math.round(subj[k].in_place_rent)) }]
        .concat(deals.map((d) => ({ name: d.name, labels: chartLabels, values: chartKeys.map((k) => Math.round(d.rows.find((x) => typeKey(x) === k).in_place_rent)) }))),
        Object.assign(chartBase("Average in-place rent by unit type"), { x: X0, y: TOP, w: 5.2, h: BOTTOM - TOP, barDir: "col", barGapWidthPct: 90, chartColors: [PRIMARY, HUSH, "A3A09A", "DEDBD4", "7A7873", ACCENT],
          showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "$#,##0", valAxisLabelFormatCode: "$#,##0", showLegend: true, legendPos: "b" }));
      const rows = [];
      const psf = (r) => (isNum(r.in_place_rent) && r.avg_sf ? `$${(r.in_place_rent / r.avg_sf).toFixed(2)}` : "-");
      const addProp = (name, asOf, rowsBy, total, fill) => {
        rows.push({ bold: true, fill: fill || CANVAS, cells: [`${name} · as of ${asOf}`, "", "", "", "", "", ""] });
        for (const k of present) {
          const r = rowsBy[k]; if (!r) continue;
          rows.push({ cells: [`   ${unitType(r)}`, int(r.units), int(r.avg_sf), money(r.market_rent), money(r.in_place_rent), psf(r), pct(r.occupied_pct)] });
        }
        if (total) rows.push({ bold: true, cells: ["   Total / avg", int(total.units), int(total.avg_sf), money(total.market_rent), money(total.in_place_rent), psf(total), pct(total.occupied_pct)] });
      };
      addProp(`${deal.name} (subject)`, rrDate, subj, um.total, TINT);
      for (const d of deals) { const by = {}; for (const r of d.rows) by[typeKey(r)] = r; addProp(`${d.name}, ${d.city}`, dateLabel(d.as_of), by, d.total); }
      const x = 6.0, w = W - X0 - x;
      const rowH = Math.min(0.3, (BOTTOM - TOP) / (rows.length + 1));
      table(s, ["Property / unit type", "Units", "Avg SF", "Market", "In-place", "In-place $/SF", "Occupied"], rows, { x, y: TOP, w, colW: [w - 4.55, 0.55, 0.6, 0.7, 0.7, 1.05, 0.95], fontSize: rowH < 0.3 ? 9 : 10, rowH });
    },
  };
  const draw = {};
  for (const id of CATALOG) draw[id] = () => { current = id; drawFns[id](); current = null; };

  return {
    CATALOG, plan, gate, draw, checks, colorNotes, shown,
    // Shared look and helpers, so a document's own slides match its blocks.
    style: { PRIMARY, ACCENT, TINT, INK, STRONG, MUTED, FAINT, HUSH, RULE, CANVAS, PAGE, FONT, DISPLAY, W, X0, CW, TOP, BOTTOM },
    fmt: { isNum, money, compact, pct, int, signedCompact, dateLabel, unitType },
    T, table, card, chartBase, evenCols, block,
    facts: { deal, snap, units, um, act, cols, pf, hcf, rrDate, modelFile, comps, hist },
  };
  }

createBlocks.CATALOG = CATALOG;
createBlocks.BLOCK_TITLES = BLOCK_TITLES;
module.exports = createBlocks;
