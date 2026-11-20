#!/usr/bin/env python3
"""Render an IC memo from a memo JSON and a brand profile JSON.

The agent gathers the data and writes memo.json (schema: references/memo-schema.md).
This script does everything that must look and compute the same on every run:
derived figures, the accuracy gate, layout, and export to HTML, PDF and Word.

Usage:
  python3 render_memo.py --memo memo.json --brand brand.json --out OUTDIR [--formats pdf,docx,html] [--force]

Exit codes: 0 = written, 2 = accuracy gate failed (nothing written unless --force), 1 = usage or render error.
"""
import argparse
import base64
import html
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
TOL = 1.0  # dollars of rounding tolerance in reconciliation checks

# Fixed design: neutrals, type scale and table styling never change with the brand.
NEUTRAL = {
    "text": "#181d27", "text_strong": "#252b37", "muted": "#414651", "faint": "#717680",
    "border": "#eaeaf0", "border_strong": "#d5d7da", "canvas": "#f5f5fa", "card": "#ffffff",
    "warn_text": "#b54708", "warn_bg": "#fffaeb", "err_text": "#b42318", "err_bg": "#fef3f2",
}
APPROVED_FONTS = {"Manrope"}  # fonts bundled in assets/fonts; anything else falls back to Manrope

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------- formatting ----------

def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt_money(v, dp=0):
    if not is_num(v):
        return "-"
    s = f"{abs(v):,.{dp}f}"
    return f"(${s})" if v < 0 else f"${s}"


def fmt_pct(v, dp=1):
    """v is a percent number (76.4 means 76.4%)."""
    return "-" if not is_num(v) else f"{v:.{dp}f}%"


def fmt_ratio_pct(v, dp=2):
    """v is a ratio (0.0525 means 5.25%)."""
    return "-" if not is_num(v) else f"{v * 100:.{dp}f}%"


def fmt_int(v):
    return "-" if not is_num(v) else f"{v:,.0f}"


def fmt_value(v, kind):
    if kind == "money":
        return fmt_money(v)
    if kind == "pct":  # ratio
        return fmt_ratio_pct(v, 1)
    if kind == "pct2":
        return fmt_ratio_pct(v, 2)
    if kind == "multiple":
        return "-" if not is_num(v) else f"{v:.2f}x"
    if kind == "years":
        return "-" if not is_num(v) else f"{v:g} yrs"
    if kind == "int":
        return fmt_int(v)
    return "-" if v is None else str(v)


def month_label(ym):
    """'2025-09' -> 'Sep 2025'."""
    try:
        y, m = ym.split("-")[:2]
        return f"{MONTHS[int(m) - 1]} {y}"
    except Exception:
        return str(ym)


def date_label(d):
    try:
        dt = datetime.strptime(d[:10], "%Y-%m-%d")
        return f"{MONTHS[dt.month - 1]} {dt.day}, {dt.year}"
    except Exception:
        return str(d)


def esc(s):
    return html.escape("" if s is None else str(s))


# ---------- color ----------

def _lum(hex_color):
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def contrast(a, b):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def valid_hex(c):
    return isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) is not None


# ---------- derived figures ----------

def derive(memo):
    """Compute every derived figure once. Returns dict; nothing here is invented, only arithmetic on inputs."""
    d = {}
    deal = memo.get("deal", {})
    units = deal.get("units")
    ops = memo.get("operations") or {}
    cols = [c["key"] for c in ops.get("columns", [])]
    price = (memo.get("pricing") or {}).get("price")
    d["price_per_unit"] = price / units if is_num(price) and is_num(units) and units else None
    d["noi_per_unit"] = {}
    d["cap_rate"] = {}
    d["expense_ratio"] = {}
    for k in cols:
        noi = (ops.get("noi") or {}).get(k)
        egr = (ops.get("egr") or {}).get(k)
        opex = (ops.get("opex") or {}).get(k)
        d["noi_per_unit"][k] = noi / units if is_num(noi) and is_num(units) and units else None
        d["cap_rate"][k] = noi / price if is_num(noi) and is_num(price) and price else None
        d["expense_ratio"][k] = opex / egr if is_num(opex) and is_num(egr) and egr else None
    # Model vs. Radix: differences are flagged, never reconciled away.
    d["recon"] = []
    for r in ((memo.get("model_reconciliation") or {}).get("rows") or []):
        rv, mv = r.get("radix"), r.get("model")
        diff = mv - rv if is_num(rv) and is_num(mv) else None
        pct = diff / abs(rv) if is_num(diff) and rv else None
        d["recon"].append({"label": r["label"], "radix": rv, "model": mv, "diff": diff, "pct": pct,
                           "format": r.get("format", "money")})
    # Auto notes: run-rate differences of more than 15% between T3 annualized and T12 (factual, derived).
    d["auto_notes"] = {}
    if "T12" in cols and "T3" in cols:
        for section in ("revenue", "expenses"):
            for row in ops.get(section, []):
                t12, t3 = row["values"].get("T12"), row["values"].get("T3")
                # Same sign only; change is in magnitude, so a smaller vacancy loss reads as a decrease.
                if is_num(t12) and is_num(t3) and abs(t12) >= 10000 and (t12 > 0) == (t3 > 0):
                    chg = (abs(t3) - abs(t12)) / abs(t12)
                    if abs(chg) >= 0.15:
                        d["auto_notes"][(section, row["label"])] = f"T3 ann. {chg * 100:+.0f}% vs T12"
    return d


# ---------- accuracy gate ----------

NUM_TOKEN = re.compile(r"\$?\(?-?\d[\d,]*(?:\.\d+)?\)?%?x?")


def figure_strings(memo, der):
    """Every figure the document shows, in the formats it shows them, plus common short forms."""
    out = set()

    def add_money(v):
        if is_num(v):
            out.add(fmt_money(v))
            out.add(fmt_money(abs(v)))
            out.add(f"{abs(v):,.0f}")
            for unit, div in (("M", 1e6), ("K", 1e3)):
                if abs(v) >= div:
                    for dp in (0, 1, 2):
                        out.add(f"${abs(v) / div:,.{dp}f}{unit}")

    def add_pct(v, dp_list=(0, 1)):
        if is_num(v):
            for dp in dp_list:
                out.add(f"{v:.{dp}f}%")

    def add_any(v):
        if is_num(v):
            out.add(f"{v:,.0f}")
            out.add(f"{v:g}")

    deal = memo.get("deal", {})
    for k in ("units", "year_built", "total_sf"):
        add_any(deal.get(k))
    snap = memo.get("snapshot") or {}
    for k, v in snap.items():
        if "pct" in k:
            add_pct(v)
        elif k.endswith("_rent"):
            add_money(v)
        else:
            add_any(v)
    ops = memo.get("operations") or {}
    for sec in ("revenue", "expenses"):
        for row in ops.get(sec, []):
            for v in row["values"].values():
                add_money(v)
    for tot in ("egr", "opex", "noi"):
        for v in (ops.get(tot) or {}).values():
            add_money(v)
    for v in der["noi_per_unit"].values():
        add_money(v)
    for v in list(der["cap_rate"].values()) + list(der["expense_ratio"].values()):
        if is_num(v):
            add_pct(v * 100, (1, 2))
    um = memo.get("unit_mix") or {}
    for r in um.get("rows", []) + ([um["total"]] if um.get("total") else []):
        add_any(r.get("units"))
        add_any(r.get("avg_sf"))
        add_money(r.get("market_rent"))
        add_money(r.get("in_place_rent"))
        add_pct(r.get("occupied_pct"))
    pr = memo.get("pricing") or {}
    add_money(pr.get("price"))
    add_money(der.get("price_per_unit"))
    for r in der.get("recon", []):
        for v in (r["radix"], r["model"], r["diff"]):
            if r["format"] == "money":
                add_money(v)
            else:
                add_any(v)
        if is_num(r["pct"]):
            add_pct(r["pct"] * 100, (0, 1))
            add_pct(abs(r["pct"]) * 100, (0, 1))
    pr_items = [{"items": pr.get("items") or []}]
    for block in pr_items + [memo.get("returns") or {}, memo.get("financing") or {}]:
        for it in (block.get("items") or []):
            v = it.get("value")
            out.add(fmt_value(v, it.get("format")))
            if it.get("format") in ("pct", "pct2") and is_num(v):
                add_pct(v * 100, (0, 1, 2))
            if it.get("format") == "money":
                add_money(v)
    return out


def normalize_token(t):
    t = t.strip().rstrip(".,;:")
    return t


def run_gate(memo, der):
    """Returns (status, checks, placeholders). status: pass | pass_with_placeholders | fail."""
    checks, placeholders = [], []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    deal = memo.get("deal", {})
    ops = memo.get("operations") or {}
    cols = [c["key"] for c in ops.get("columns", [])]

    # 1. Operating statement ties out in every column.
    for k in cols:
        rev = sum(r["values"].get(k) or 0 for r in ops.get("revenue", []))
        exp = sum(r["values"].get(k) or 0 for r in ops.get("expenses", []))
        egr, opex, noi = (ops.get("egr") or {}).get(k), (ops.get("opex") or {}).get(k), (ops.get("noi") or {}).get(k)
        if is_num(egr):
            check(f"{k}: revenue lines sum to EGR", abs(rev - egr) <= TOL, f"lines {rev:,.2f} vs EGR {egr:,.2f}")
        if is_num(opex):
            check(f"{k}: expense lines sum to OpEx", abs(exp - opex) <= TOL, f"lines {exp:,.2f} vs OpEx {opex:,.2f}")
        if is_num(noi) and is_num(egr) and is_num(opex):
            check(f"{k}: NOI = EGR - OpEx", abs(egr - opex - noi) <= TOL, f"{egr - opex:,.2f} vs NOI {noi:,.2f}")

    # 2. Unit count matches across the deal header and the unit mix.
    um = memo.get("unit_mix") or {}
    if um.get("rows"):
        row_units = sum(r.get("units") or 0 for r in um["rows"])
        tot_units = (um.get("total") or {}).get("units")
        check("Unit mix rows add to the unit mix total", tot_units is None or row_units == tot_units, f"{row_units} vs {tot_units}")
        check("Unit mix total matches the deal unit count", tot_units == deal.get("units"), f"{tot_units} vs {deal.get('units')}")

    # 3. Occupancy shown in the snapshot matches the unit mix total.
    snap = memo.get("snapshot") or {}
    if is_num(snap.get("occupancy_pct")) and is_num((um.get("total") or {}).get("occupied_pct")):
        check("Snapshot occupancy matches the unit mix total",
              abs(snap["occupancy_pct"] - um["total"]["occupied_pct"]) < 0.05,
              f"{snap['occupancy_pct']:.2f}% vs {um['total']['occupied_pct']:.2f}%")

    # 4. Every table has a source and an as-of date.
    src = memo.get("sources") or {}
    check("Rent roll as-of date is stated", bool((src.get("rent_roll") or {}).get("as_of")) or not um.get("rows"))
    check("Operating statement windows are stated",
          all((c.get("window") for c in ops.get("columns", [])))) if cols else None
    for block in ("returns", "financing", "sensitivity"):
        b = memo.get(block)
        if b:
            ok = b.get("source") in ("client_model", "radix", "user") and (b.get("source") != "client_model" or (src.get("client_model") or {}).get("file"))
            check(f"{block.title()} names its source", ok, b.get("source", "no source"))

    # 5. Numbers in narrative text exist in the data.
    figs = figure_strings(memo, der)
    narrative = [("Commentary", (memo.get("commentary") or {}).get("text") or "")]
    for i, r in enumerate(memo.get("risks") or []):
        narrative.append((f"Risk {i + 1}", f"{r.get('risk', '')} {r.get('mitigant') or ''}"))
    for name, text in narrative:
        unmatched = []
        for tok in NUM_TOKEN.findall(text):
            t = normalize_token(tok)
            bare = t.strip("()$")
            if re.fullmatch(r"\d{1,2}", bare) or re.fullmatch(r"(19|20)\d\d", bare):
                continue  # small counts and years are not figures
            if t not in figs and bare not in figs and f"${bare}" not in figs:
                unmatched.append(t)
        check(f"{name}: every figure is in the data", not unmatched, ", ".join(unmatched))

    # 6. Placeholders.
    pr = memo.get("pricing") or {}
    if not is_num(pr.get("price")):
        placeholders.append("Price (needed for price per unit and cap rates). Source: client model or user.")
    for block, label in (("returns", "Returns"), ("financing", "Financing and JV"), ("sensitivity", "IRR sensitivity")):
        if not memo.get(block):
            placeholders.append(f"{label}. Source: client model.")
    if not memo.get("assumptions_vs_market"):
        placeholders.append("Assumptions vs. submarket forecast. Source: client model plus a submarket forecast (not in Radix yet).")
    if not (memo.get("commentary") or {}).get("text"):
        placeholders.append("Transaction commentary.")

    checks = [c for c in checks if c]
    failed = [c for c in checks if not c["ok"]]
    status = "fail" if failed else ("pass_with_placeholders" if placeholders else "pass")
    return status, checks, placeholders


# ---------- HTML ----------

def font_face_css():
    css = []
    for w in (400, 500, 600, 700, 800):
        p = ASSETS / "fonts" / f"manrope-latin-{w}-normal.woff2"
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode()
            css.append(f"@font-face{{font-family:'Manrope';font-weight:{w};font-style:normal;"
                       f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    return "\n".join(css)


def placeholder_html(label, source="client model"):
    return (f'<div class="ph"><span class="ph-tag">Needs {esc(source)}</span>'
            f'<span class="ph-text">{esc(label)}</span></div>')


def source_line(text):
    return f'<div class="src">{esc(text)}</div>'


def kv_table(items):
    rows = "".join(f'<tr><td>{esc(it["label"])}</td><td class="n">{esc(fmt_value(it.get("value"), it.get("format")))}</td></tr>'
                   for it in items)
    return f'<table class="kv">{rows}</table>'


def build_html(memo, brand, der, status, placeholders):
    deal = memo["deal"]
    colors = brand.get("colors", {})
    primary = colors.get("primary") if valid_hex(colors.get("primary")) else "#144a85"
    accent = colors.get("accent") if valid_hex(colors.get("accent")) else "#1f76d6"
    tint = colors.get("accent_tint") if valid_hex(colors.get("accent_tint")) else "#eff4fe"
    on_primary = "#ffffff" if contrast(primary, "#ffffff") >= 4.5 else NEUTRAL["text"]
    font = brand.get("fonts", {}).get("body", "Manrope")
    font = font if font in APPROVED_FONTS else "Manrope"
    src = memo.get("sources") or {}
    ops = memo.get("operations") or {}
    cols = ops.get("columns", [])
    units = deal.get("units")
    model = src.get("client_model") or {}
    model_label = f'Client model: {model.get("file")}' + (f' ({model["as_of"]})' if model.get("as_of") else "") if model.get("file") else None

    # Logo or wordmark
    logo = brand.get("logo") or {}
    if logo.get("data_uri"):
        logo_html = f'<img class="logo" src="{esc(logo["data_uri"])}" alt="">'
    else:
        logo_html = f'<div class="wordmark">{esc(logo.get("wordmark_text") or brand.get("firm", {}).get("display_name") or "")}</div>'

    # Header facts
    facts = [f"{fmt_int(units)} units"]
    if deal.get("year_built"):
        facts.append(f"Built {deal['year_built']}")
    if deal.get("building_type"):
        facts.append(deal["building_type"])
    if deal.get("total_sf"):
        facts.append(f"{fmt_int(deal['total_sf'])} SF")
    if deal.get("market"):
        facts.append(deal["market"])

    # Snapshot tiles
    snap = memo.get("snapshot") or {}
    t12_noi = (ops.get("noi") or {}).get("T12")
    tiles = [
        ("Occupancy", fmt_pct(snap.get("occupancy_pct")), f"Rent roll {date_label(src.get('rent_roll', {}).get('as_of', ''))}"),
        ("Avg in-place rent", fmt_money(snap.get("in_place_rent")), f"{fmt_pct(snap.get('pct_of_market'))} of market"),
        ("Avg market rent", fmt_money(snap.get("market_rent")), "Rent roll"),
        ("T12 NOI", fmt_money(t12_noi), f"{fmt_money(der['noi_per_unit'].get('T12'))} / unit"),
    ]
    tiles_html = "".join(f'<div class="tile"><div class="tl">{esc(a)}</div><div class="tv">{esc(b)}</div><div class="ts">{esc(c)}</div></div>'
                         for a, b, c in tiles)

    # Commentary
    com = memo.get("commentary") or {}
    if com.get("text"):
        paras = "".join(f"<p>{esc(p)}</p>" for p in com["text"].split("\n") if p.strip())
        com_html = paras + ('<div class="draft">Draft for analyst review</div>' if com.get("status", "draft") == "draft" else "")
    else:
        com_html = placeholder_html("Transaction commentary", "analyst")

    # Pricing
    pr = memo.get("pricing") or {}
    if is_num(pr.get("price")):
        rows = [(pr.get("price_label") or "Price", fmt_money(pr["price"])), ("Price / unit", fmt_money(der["price_per_unit"]))]
        for c in cols:
            rows.append((f"Cap rate on Radix {c['label']} NOI", fmt_ratio_pct(der["cap_rate"].get(c["key"]))))
        for it in pr.get("items") or []:
            rows.append((it["label"], fmt_value(it.get("value"), it.get("format"))))
        price_src = {"client_model": model_label or "Client model", "radix": "Radix deal pricing", "user": "Entered by user"}.get(pr.get("price_source"), "")
        extra = " Rows after the cap rates are from the model." if pr.get("items") else ""
        pricing_html = ('<table class="kv">' + "".join(f'<tr><td>{esc(a)}</td><td class="n">{esc(b)}</td></tr>' for a, b in rows) +
                        '</table>' + source_line(f"Price: {price_src}. Cap rates derived: Radix NOI / price.{extra}"))
    else:
        pricing_html = placeholder_html("Price, price per unit and cap rates on T12, T3 and T1 NOI")

    # Model vs. Radix
    if der["recon"]:
        mr = memo.get("model_reconciliation") or {}
        def rc(v, f):
            return fmt_money(v) if f == "money" else fmt_int(v)
        def recon_row(r):
            f = r["format"]
            flag = "flag" if is_num(r["pct"]) and abs(r["pct"]) >= 0.05 else ""
            diff = "-"
            if is_num(r["diff"]):
                diff = ("+" if r["diff"] > 0 else "") + rc(r["diff"], f)
                if is_num(r["pct"]) and r["diff"]:
                    diff += f" ({r['pct'] * 100:+.1f}%)"
            return (f'<tr class="{flag}"><td>{esc(r["label"])}</td><td class="n">{esc(rc(r["radix"], f))}</td>'
                    f'<td class="n">{esc(rc(r["model"], f))}</td><td class="n">{esc(diff)}</td></tr>')
        body_r = "".join(recon_row(r) for r in der["recon"])
        recon_html = (f'<table class="ops"><thead><tr><th>Line</th><th class="n">Radix {esc(mr.get("radix_basis", ""))}</th>'
                      f'<th class="n">Model {esc(mr.get("model_basis", ""))}</th><th class="n">Difference</th></tr></thead><tbody>{body_r}</tbody></table>'
                      + source_line(f"Differences of 5% or more are highlighted. Derived: model minus Radix. {model_label or ''}"))
    else:
        recon_html = None

    def block_or_ph(key, label):
        b = memo.get(key)
        if not b or not b.get("items"):
            return placeholder_html(label)
        return kv_table(b["items"]) + source_line(model_label or "Client model")

    returns_html = block_or_ph("returns", "Levered and unlevered IRR, equity multiple, cash-on-cash")
    financing_html = block_or_ph("financing", "Loan amount, LTV, rate, term, interest-only period, equity and JV split")

    # Operating cash flow
    head = "".join(f'<th class="n">{esc(c["label"])}</th>' for c in cols)
    def ops_rows(section):
        out = []
        for r in ops.get(section, []):
            vals = "".join(f'<td class="n">{esc(fmt_money(r["values"].get(c["key"])))}</td>' for c in cols)
            note = r.get("note") or der["auto_notes"].get((section, r["label"]), "")
            note_cls = "note" if r.get("note") else "note derived"
            out.append(f'<tr><td>{esc(r["label"])}</td>{vals}<td class="{note_cls}">{esc(note)}</td></tr>')
        return "".join(out)

    def total_row(label, key, cls):
        vals = "".join(f'<td class="n">{esc(fmt_money((ops.get(key) or {}).get(c["key"])))}</td>' for c in cols)
        return f'<tr class="{cls}"><td>{esc(label)}</td>{vals}<td></td></tr>'

    per_unit = "".join(f'<td class="n">{esc(fmt_money(der["noi_per_unit"].get(c["key"])))}</td>' for c in cols)
    ratio = "".join(f'<td class="n">{esc(fmt_ratio_pct(der["expense_ratio"].get(c["key"]), 1))}</td>' for c in cols)
    windows = "; ".join(f'{c["label"]} {c["window"]}' for c in cols if c.get("window"))
    ops_html = f"""
<table class="ops">
<thead><tr><th>Operating cash flow</th>{head}<th class="notecol">Notes</th></tr></thead>
<tbody>
<tr class="sec"><td colspan="{len(cols) + 2}">Revenue</td></tr>
{ops_rows("revenue")}
{total_row("Effective gross revenue", "egr", "tot")}
<tr class="sec"><td colspan="{len(cols) + 2}">Operating expenses</td></tr>
{ops_rows("expenses")}
{total_row("Total operating expenses", "opex", "tot")}
{total_row("Net operating income", "noi", "noi")}
<tr class="sub"><td>NOI / unit (derived)</td>{per_unit}<td></td></tr>
<tr class="sub"><td>Expense ratio (derived)</td>{ratio}<td></td></tr>
</tbody></table>
{source_line(f"Radix operating statement, {(src.get('operating_statement') or {}).get('label', 'Actuals')}, mapped. {windows}. Notes in grey are derived run-rate flags.")}"""

    # Unit mix
    um = memo.get("unit_mix") or {}
    if um.get("rows"):
        def um_row(r, cls=""):
            return (f'<tr class="{cls}"><td>{esc(r.get("label", "Total"))}</td><td class="n">{fmt_int(r.get("units"))}</td>'
                    f'<td class="n">{fmt_int(r.get("avg_sf"))}</td><td class="n">{fmt_money(r.get("market_rent"))}</td>'
                    f'<td class="n">{fmt_money(r.get("in_place_rent"))}</td><td class="n">{fmt_pct(r.get("occupied_pct"))}</td></tr>')
        body = "".join(um_row(r) for r in um["rows"]) + (um_row({**um["total"], "label": "Total / avg"}, "tot") if um.get("total") else "")
        um_html = (f'<table class="ops"><thead><tr><th>Unit mix</th><th class="n">Units</th><th class="n">Avg SF</th>'
                   f'<th class="n">Market</th><th class="n">In-place</th><th class="n">Occ.</th></tr></thead><tbody>{body}</tbody></table>'
                   + source_line(f"Radix rent roll as of {date_label(src.get('rent_roll', {}).get('as_of', ''))}, contractual rent."))
    else:
        um_html = placeholder_html("Unit mix", "rent roll")

    # Sensitivity
    sens = memo.get("sensitivity")
    if sens and sens.get("values"):
        fmt = sens.get("format", "pct")
        head_s = "".join(f'<th class="n">{esc(c)}</th>' for c in sens["cols"])
        body_s = "".join(
            f'<tr><td class="rl">{esc(rl)}</td>' + "".join(f'<td class="n">{esc(fmt_value(v, fmt))}</td>' for v in rowv) + "</tr>"
            for rl, rowv in zip(sens["rows"], sens["values"]))
        sens_html = (f'<div class="gtitle">{esc(sens.get("title", "Sensitivity"))}</div>'
                     f'<table class="grid"><thead><tr><th class="corner">{esc(sens.get("row_label", ""))} \\ {esc(sens.get("col_label", ""))}</th>{head_s}</tr></thead>'
                     f'<tbody>{body_s}</tbody></table>' + source_line(model_label or "Client model"))
    else:
        sens_html = placeholder_html("IRR sensitivity grid (for example exit cap rate vs. rent growth)")

    # Assumptions vs. submarket
    avm = memo.get("assumptions_vs_market")
    if avm and avm.get("rows"):
        body_a = "".join(f'<tr><td>{esc(r["label"])}</td><td class="n">{esc(r.get("ours", "-"))}</td><td class="n">{esc(r.get("market", "-"))}</td></tr>' for r in avm["rows"])
        avm_html = (f'<table class="ops"><thead><tr><th>Assumption</th><th class="n">Underwritten</th><th class="n">Submarket</th></tr></thead><tbody>{body_a}</tbody></table>'
                    + source_line(avm.get("source", "")))
    else:
        avm_html = placeholder_html("Underwritten rent growth, vacancy and expense growth next to a submarket forecast", "client model + forecast")

    # Risks
    risks = memo.get("risks") or []
    if risks:
        risks_html = "<ul class='risks'>" + "".join(
            f"<li><b>{esc(r['risk'])}</b>" + (f"<br><span class='mit'>Mitigant: {esc(r['mitigant'])}</span>" if r.get("mitigant") else "<br><span class='mit todo'>Mitigant: analyst to add</span>") + "</li>"
            for r in risks) + "</ul><div class='draft'>Draft for analyst review</div>"
    else:
        risks_html = placeholder_html("Key risks and mitigants", "analyst")

    # Footer sources
    srcs = [f"Account: {memo.get('account', '-')}"]
    if src.get("rent_roll", {}).get("as_of"):
        srcs.append(f"Rent roll as of {date_label(src['rent_roll']['as_of'])}")
    if cols:
        srcs.append(f"Operating statement {windows}")
    if model_label:
        srcs.append(model_label)
    disclaimer = brand.get("disclaimer") or ""
    sample_banner = '<div class="sample">SAMPLE: returns, financing and sensitivity use an illustrative model, not a client file</div>' if memo.get("sample") else ""
    status_label = memo.get("status_label") or "Screening memo"

    css = f"""
{font_face_css()}
@page {{ size: Letter; margin: 0.35in 0.4in 0.45in 0.4in; }}
* {{ box-sizing: border-box; }}
html, body {{ margin:0; padding:0; background:#fff; }}
body {{ font-family:'{font}', Arial, sans-serif; color:{NEUTRAL['text']}; font-size:7.6pt; line-height:1.32; letter-spacing:-0.006em;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; font-variant-numeric: tabular-nums; }}
.hdr {{ background:{primary}; color:{on_primary}; border-radius:6px; padding:10px 14px 9px; display:flex; justify-content:space-between; align-items:flex-end; }}
.hdr .left {{ display:flex; flex-direction:column; gap:3px; }}
.wordmark {{ font-weight:800; font-size:11pt; letter-spacing:-0.02em; opacity:.95; }}
.logo {{ max-height:22px; max-width:140px; }}
.dname {{ font-weight:800; font-size:17pt; letter-spacing:-0.02em; line-height:1.1; margin-top:4px; }}
.daddr {{ font-size:8pt; opacity:.9; }}
.dfacts {{ font-size:7.6pt; opacity:.9; }}
.hdr .right {{ text-align:right; font-size:7.6pt; }}
.hdr .doc {{ font-weight:700; font-size:9.5pt; }}
.sample {{ margin-top:6px; background:{NEUTRAL['warn_bg']}; color:{NEUTRAL['warn_text']}; font-weight:700; padding:4px 8px; border-radius:4px; font-size:7.4pt; }}
.row {{ display:grid; gap:10px; margin-top:9px; }}
.r1 {{ grid-template-columns: 1.55fr 1fr; }}
.r2 {{ grid-template-columns: 1fr 1fr 1fr; }}
.r3 {{ grid-template-columns: 1.62fr 1fr; }}
.r4 {{ grid-template-columns: 1.62fr 1fr; }}
.card {{ border:1px solid {NEUTRAL['border']}; border-radius:6px; padding:8px 10px; break-inside:avoid; }}
h3 {{ margin:0 0 5px; font-size:7.4pt; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:{primary}; display:flex; align-items:center; gap:6px; }}
h3::before {{ content:""; width:3px; height:9px; background:{accent}; border-radius:2px; display:inline-block; }}
p {{ margin:0 0 5px; }}
.tiles {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; }}
.tile {{ background:{tint}; border-radius:5px; padding:6px 8px; }}
.tl {{ font-size:6.8pt; color:{NEUTRAL['muted']}; font-weight:600; }}
.tv {{ font-size:12pt; font-weight:800; color:{NEUTRAL['text_strong']}; letter-spacing:-0.02em; }}
.ts {{ font-size:6.6pt; color:{NEUTRAL['faint']}; }}
table {{ width:100%; border-collapse:collapse; }}
.kv td {{ padding:2.5px 0; border-bottom:1px solid {NEUTRAL['border']}; }}
.kv tr:last-child td {{ border-bottom:0; }}
td.n, th.n {{ text-align:right; white-space:nowrap; }}
.ops th {{ font-size:6.8pt; font-weight:700; color:{NEUTRAL['faint']}; text-align:left; padding:3px 4px; border-bottom:1.5px solid {NEUTRAL['border_strong']}; }}
.ops th:first-child {{ color:{primary}; text-transform:uppercase; letter-spacing:.06em; font-size:7.2pt; }}
.ops td {{ padding:1.6px 4px; border-bottom:1px solid {NEUTRAL['border']}; }}
.ops tr.sec td {{ font-weight:700; color:{NEUTRAL['muted']}; padding-top:4px; border-bottom:0; font-size:6.9pt; text-transform:uppercase; letter-spacing:.04em; }}
.ops tr.tot td {{ font-weight:700; border-top:1px solid {NEUTRAL['border_strong']}; }}
.ops tr.noi td {{ font-weight:800; background:{tint}; color:{NEUTRAL['text_strong']}; border-top:1.5px solid {primary}; }}
.ops tr.flag td {{ background:{NEUTRAL['warn_bg']}; color:{NEUTRAL['warn_text']}; font-weight:600; }}
.ops tr.sub td {{ color:{NEUTRAL['muted']}; font-style:normal; }}
.ops .notecol {{ width:22%; }}
td.note {{ color:{NEUTRAL['text']}; font-size:6.8pt; }}
td.note.derived {{ color:{NEUTRAL['faint']}; }}
.grid th, .grid td {{ padding:2px 4px; border:1px solid {NEUTRAL['border']}; font-size:7pt; }}
.grid th {{ background:{tint}; font-weight:700; }}
.grid td.rl {{ font-weight:700; background:{tint}; }}
.grid th.corner {{ text-align:left; font-size:6.4pt; color:{NEUTRAL['muted']}; }}
.gtitle {{ font-weight:600; margin-bottom:3px; }}
.src {{ margin-top:4px; font-size:6.4pt; color:{NEUTRAL['faint']}; }}
.ph {{ border:1px dashed {NEUTRAL['warn_text']}; background:{NEUTRAL['warn_bg']}; border-radius:5px; padding:6px 8px; display:flex; flex-direction:column; gap:2px; }}
.ph-tag {{ font-size:6.4pt; font-weight:700; color:{NEUTRAL['warn_text']}; text-transform:uppercase; letter-spacing:.05em; }}
.ph-text {{ color:{NEUTRAL['muted']}; }}
.draft {{ display:inline-block; margin-top:2px; font-size:6.4pt; font-weight:700; color:{NEUTRAL['warn_text']}; text-transform:uppercase; letter-spacing:.05em; }}
.risks {{ margin:0; padding-left:12px; }}
.risks li {{ margin-bottom:4px; }}
.mit {{ color:{NEUTRAL['muted']}; }}
.mit.todo {{ color:{NEUTRAL['warn_text']}; }}
.stack {{ display:flex; flex-direction:column; gap:10px; }}
.foot {{ margin-top:9px; padding-top:5px; border-top:1px solid {NEUTRAL['border_strong']}; font-size:6.3pt; color:{NEUTRAL['faint']}; display:flex; justify-content:space-between; gap:16px; }}
.foot .disc {{ max-width:70%; }}
"""

    body = f"""
<div class="hdr">
  <div class="left">{logo_html}
    <div class="dname">{esc(deal.get('name'))}</div>
    <div class="daddr">{esc(deal.get('address'))}</div>
    <div class="dfacts">{esc(' · '.join(facts))}</div>
  </div>
  <div class="right"><div class="doc">Investment Committee</div><div>{esc(status_label)}</div><div>{esc(date_label(memo.get('memo_date', date.today().isoformat())))}</div></div>
</div>
{sample_banner}
<div class="row r1">
  <div class="card"><h3>Transaction commentary</h3>{com_html}</div>
  <div class="card"><h3>Snapshot</h3><div class="tiles">{tiles_html}</div></div>
</div>
<div class="row r2">
  <div class="card"><h3>Pricing</h3>{pricing_html}</div>
  <div class="card"><h3>Returns</h3>{returns_html}</div>
  <div class="card"><h3>Financing and JV</h3>{financing_html}</div>
</div>
<div class="row r3">
  <div class="card">{ops_html}</div>
  <div class="stack">
    <div class="card">{um_html}</div>
    {f'<div class="card"><h3>Model vs. Radix</h3>{recon_html}</div>' if recon_html else ''}
    <div class="card"><h3>Returns sensitivity</h3>{sens_html}</div>
  </div>
</div>
<div class="row r4">
  <div class="card"><h3>Risks and mitigants</h3>{risks_html}</div>
  <div class="card"><h3>Assumptions vs. submarket</h3>{avm_html}</div>
</div>
<div class="foot"><div class="disc">{esc(disclaimer)}</div><div>{esc(' · '.join(srcs))}</div></div>
"""
    title = f"{deal.get('name')} IC memo"
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(title)}</title><style>{css}</style></head><body>{body}</body></html>"


# ---------- PDF ----------

def write_pdf(html_path, pdf_path, one_page=False):
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto(html_path.resolve().as_uri())
            pg.wait_for_timeout(200)
            # Shrink in small steps until the memo prints on one page; never below 72%.
            # Printing and counting pages is exact, unlike measuring the screen layout.
            scales = [1.0, 0.96, 0.92, 0.88, 0.84, 0.8, 0.76, 0.72] if one_page else [1.0]
            for scale in scales:
                pdf = pg.pdf(format="Letter", print_background=True, prefer_css_page_size=True, scale=scale)
                if len(re.findall(rb"/Type\s*/Page[^s]", pdf)) <= 1:
                    break
            Path(pdf_path).write_bytes(pdf)
            b.close()
        return "playwright"
    except ImportError:
        pass
    try:
        import weasyprint
        weasyprint.HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return "weasyprint"
    except ImportError:
        return None


# ---------- DOCX ----------

def write_docx(memo, brand, der, docx_path):
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor, Inches

    colors = brand.get("colors", {})
    primary = colors.get("primary") if valid_hex(colors.get("primary")) else "#144a85"
    tint = colors.get("accent_tint") if valid_hex(colors.get("accent_tint")) else "#eff4fe"
    font = brand.get("fonts", {}).get("body", "Manrope")
    rgb = lambda h: RGBColor.from_string(h.lstrip("#").upper())

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    for side in ("left_margin", "right_margin"):
        setattr(sec, side, Inches(0.6))
    sec.top_margin, sec.bottom_margin = Inches(0.5), Inches(0.5)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = font, Pt(9)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), font)
    st.paragraph_format.space_after = Pt(3)

    def shade(cell, hex_color):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color.lstrip("#"))
        tcPr.append(shd)

    def heading(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(text.upper())
        r.bold, r.font.size, r.font.color.rgb = True, Pt(8.5), rgb(primary)
        return p

    def small(text, color="#717680"):
        p = doc.add_paragraph()
        r = p.add_run(text)
        r.font.size, r.font.color.rgb = Pt(7), rgb(color)
        return p

    def placeholder(text, source="client model"):
        p = doc.add_paragraph()
        r = p.add_run(f"[Needs {source}] ")
        r.bold, r.font.color.rgb, r.font.size = True, rgb("#b54708"), Pt(8)
        r2 = p.add_run(text)
        r2.font.size = Pt(8)

    def table(headers, rows, num_cols=(), bold_rows=(), shade_rows=()):
        t = doc.add_table(rows=1, cols=len(headers))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.style = "Table Grid"
        for i, h in enumerate(headers):
            c = t.rows[0].cells[i]
            c.text = ""
            r = c.paragraphs[0].add_run(h)
            r.bold, r.font.size = True, Pt(7.5)
            if i in num_cols:
                c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            shade(c, tint)
        for ri, row in enumerate(rows):
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = ""
                r = cells[i].paragraphs[0].add_run(str(v))
                r.font.size = Pt(7.5)
                r.bold = ri in bold_rows
                if i in num_cols:
                    cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                if ri in shade_rows:
                    shade(cells[i], tint)
        return t

    deal, src, ops = memo["deal"], memo.get("sources") or {}, memo.get("operations") or {}
    cols = ops.get("columns", [])
    model = src.get("client_model") or {}
    model_label = f'Client model: {model.get("file")}' if model.get("file") else "Client model"

    # Header band
    hb = doc.add_table(rows=1, cols=2)
    hb.alignment = WD_TABLE_ALIGNMENT.CENTER
    for c in hb.rows[0].cells:
        shade(c, primary)
    on = "#ffffff" if contrast(primary, "#ffffff") >= 4.5 else NEUTRAL["text"]
    left, right = hb.rows[0].cells
    left.text = ""
    p = left.paragraphs[0]
    r = p.add_run((brand.get("logo") or {}).get("wordmark_text") or brand.get("firm", {}).get("display_name", ""))
    r.bold, r.font.size, r.font.color.rgb = True, Pt(10), rgb(on)
    p2 = left.add_paragraph()
    r = p2.add_run(deal.get("name", ""))
    r.bold, r.font.size, r.font.color.rgb = True, Pt(18), rgb(on)
    p3 = left.add_paragraph()
    facts = [deal.get("address", ""), f"{fmt_int(deal.get('units'))} units"]
    if deal.get("year_built"):
        facts.append(f"Built {deal['year_built']}")
    if deal.get("building_type"):
        facts.append(deal["building_type"])
    r = p3.add_run(" · ".join(facts))
    r.font.size, r.font.color.rgb = Pt(8), rgb(on)
    right.text = ""
    for i, line in enumerate(["Investment Committee", memo.get("status_label") or "Screening memo", date_label(memo.get("memo_date", ""))]):
        pp = right.paragraphs[0] if i == 0 else right.add_paragraph()
        pp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        rr = pp.add_run(line)
        rr.bold = i == 0
        rr.font.size, rr.font.color.rgb = Pt(8.5), rgb(on)
    if memo.get("sample"):
        small("SAMPLE: returns, financing and sensitivity use an illustrative model, not a client file", "#b54708")

    heading("Transaction commentary")
    com = memo.get("commentary") or {}
    if com.get("text"):
        for para in [x for x in com["text"].split("\n") if x.strip()]:
            doc.add_paragraph(para)
        small("Draft for analyst review", "#b54708")
    else:
        placeholder("Transaction commentary", "analyst")

    heading("Snapshot")
    snap = memo.get("snapshot") or {}
    table(["Occupancy", "Avg in-place rent", "Avg market rent", "In-place % of market", "T12 NOI", "T12 NOI / unit"],
          [[fmt_pct(snap.get("occupancy_pct")), fmt_money(snap.get("in_place_rent")), fmt_money(snap.get("market_rent")),
            fmt_pct(snap.get("pct_of_market")), fmt_money((ops.get("noi") or {}).get("T12")), fmt_money(der["noi_per_unit"].get("T12"))]],
          num_cols=range(6))

    heading("Pricing")
    pr = memo.get("pricing") or {}
    if is_num(pr.get("price")):
        rows = [[pr.get("price_label") or "Price", fmt_money(pr["price"])], ["Price / unit", fmt_money(der["price_per_unit"])]]
        rows += [[f"Cap rate on Radix {c['label']} NOI", fmt_ratio_pct(der["cap_rate"].get(c["key"]))] for c in cols]
        rows += [[it["label"], fmt_value(it.get("value"), it.get("format"))] for it in pr.get("items") or []]
        table(["Item", "Value"], rows, num_cols=(1,))
        small("Cap rates derived: Radix NOI / price." + (" Rows after the cap rates are from the model." if pr.get("items") else ""))
    else:
        placeholder("Price, price per unit and cap rates on T12, T3 and T1 NOI")

    if der["recon"]:
        mr = memo.get("model_reconciliation") or {}
        heading("Model vs. Radix")
        rc = lambda v, f: fmt_money(v) if f == "money" else fmt_int(v)
        table(["Line", f"Radix {mr.get('radix_basis', '')}", f"Model {mr.get('model_basis', '')}", "Difference"],
              [[r["label"], rc(r["radix"], r["format"]), rc(r["model"], r["format"]),
                (("+" if is_num(r["diff"]) and r["diff"] > 0 else "") + rc(r["diff"], r["format"]) + (f" ({r['pct'] * 100:+.1f}%)" if is_num(r["pct"]) and r["diff"] else "")) if is_num(r["diff"]) else "-"]
               for r in der["recon"]], num_cols=(1, 2, 3))
        small("Derived: model minus Radix.")

    for key, label, ph in (("returns", "Returns", "Levered and unlevered IRR, equity multiple, cash-on-cash"),
                           ("financing", "Financing and JV", "Loan amount, LTV, rate, term, interest-only period, equity and JV split")):
        heading(label)
        b = memo.get(key)
        if b and b.get("items"):
            table(["Item", "Value"], [[it["label"], fmt_value(it.get("value"), it.get("format"))] for it in b["items"]], num_cols=(1,))
            small(model_label)
        else:
            placeholder(ph)

    heading("Operating cash flow")
    hdrs = ["Line"] + [c["label"] for c in cols] + ["Notes"]
    rows, bold, shaded = [], [], []
    def add_sec(name):
        rows.append([name] + [""] * (len(cols) + 1))
        bold.append(len(rows) - 1)
    def add_lines(section):
        for r in ops.get(section, []):
            note = r.get("note") or der["auto_notes"].get((section, r["label"]), "")
            rows.append([r["label"]] + [fmt_money(r["values"].get(c["key"])) for c in cols] + [note])
    def add_tot(label, key, shade_it=False):
        rows.append([label] + [fmt_money((ops.get(key) or {}).get(c["key"])) for c in cols] + [""])
        bold.append(len(rows) - 1)
        if shade_it:
            shaded.append(len(rows) - 1)
    add_sec("Revenue"); add_lines("revenue"); add_tot("Effective gross revenue", "egr")
    add_sec("Operating expenses"); add_lines("expenses"); add_tot("Total operating expenses", "opex")
    add_tot("Net operating income", "noi", True)
    rows.append(["NOI / unit (derived)"] + [fmt_money(der["noi_per_unit"].get(c["key"])) for c in cols] + [""])
    rows.append(["Expense ratio (derived)"] + [fmt_ratio_pct(der["expense_ratio"].get(c["key"]), 1) for c in cols] + [""])
    table(hdrs, rows, num_cols=range(1, len(cols) + 1), bold_rows=bold, shade_rows=shaded)
    windows = "; ".join(f'{c["label"]} {c["window"]}' for c in cols if c.get("window"))
    small(f"Radix operating statement, {(src.get('operating_statement') or {}).get('label', 'Actuals')}. {windows}. Notes column is for the analyst; pre-filled notes are derived run-rate flags.")

    heading("Unit mix")
    um = memo.get("unit_mix") or {}
    if um.get("rows"):
        rws = [[r["label"], fmt_int(r.get("units")), fmt_int(r.get("avg_sf")), fmt_money(r.get("market_rent")), fmt_money(r.get("in_place_rent")), fmt_pct(r.get("occupied_pct"))] for r in um["rows"]]
        if um.get("total"):
            t = um["total"]
            rws.append(["Total / avg", fmt_int(t.get("units")), fmt_int(t.get("avg_sf")), fmt_money(t.get("market_rent")), fmt_money(t.get("in_place_rent")), fmt_pct(t.get("occupied_pct"))])
        table(["Unit type", "Units", "Avg SF", "Market", "In-place", "Occ."], rws, num_cols=range(1, 6), bold_rows=(len(rws) - 1,) if um.get("total") else ())
        small(f"Radix rent roll as of {date_label(src.get('rent_roll', {}).get('as_of', ''))}, contractual rent.")

    heading("Returns sensitivity")
    sens = memo.get("sensitivity")
    if sens and sens.get("values"):
        small(sens.get("title", ""), NEUTRAL["text"])
        table([f"{sens.get('row_label', '')} \\ {sens.get('col_label', '')}"] + list(sens["cols"]),
              [[rl] + [fmt_value(v, sens.get("format", "pct")) for v in rv] for rl, rv in zip(sens["rows"], sens["values"])],
              num_cols=range(1, len(sens["cols"]) + 1))
        small(model_label)
    else:
        placeholder("IRR sensitivity grid (for example exit cap rate vs. rent growth)")

    heading("Assumptions vs. submarket")
    avm = memo.get("assumptions_vs_market")
    if avm and avm.get("rows"):
        table(["Assumption", "Underwritten", "Submarket"], [[r["label"], r.get("ours", "-"), r.get("market", "-")] for r in avm["rows"]], num_cols=(1, 2))
    else:
        placeholder("Underwritten rent growth, vacancy and expense growth next to a submarket forecast", "client model + forecast")

    heading("Risks and mitigants")
    for r in memo.get("risks") or []:
        p = doc.add_paragraph(style="List Bullet")
        rr = p.add_run(r["risk"])
        rr.bold = True
        p.add_run(f"\nMitigant: {r['mitigant']}" if r.get("mitigant") else "\nMitigant: analyst to add")
    if memo.get("risks"):
        small("Draft for analyst review", "#b54708")

    small(" ")
    small(brand.get("disclaimer") or "")
    doc.save(str(docx_path))


# ---------- run summary ----------

def run_summary(memo, status, checks, placeholders, outputs):
    lines = [f"# Run summary: {memo['deal'].get('name')} IC memo", "",
             f"Accuracy gate: **{status.replace('_', ' ')}**", "", "## Checks"]
    for c in checks:
        lines.append(f"- {'PASS' if c['ok'] else 'FAIL'}: {c['check']}" + (f" ({c['detail']})" if c["detail"] and not c["ok"] else ""))
    lines += ["", "## Placeholders (missing data, flagged in the document)"]
    lines += [f"- {p}" for p in placeholders] or ["- None"]
    lines += ["", "## Files"] + [f"- {o}" for o in outputs]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--memo", required=True)
    ap.add_argument("--brand", default=str(ASSETS / "brand-radix-default.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--formats", default="pdf")
    ap.add_argument("--force", action="store_true", help="write files even if the accuracy gate fails")
    a = ap.parse_args()

    memo = json.loads(Path(a.memo).read_text())
    brand = json.loads(Path(a.brand).read_text())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    der = derive(memo)
    status, checks, placeholders = run_gate(memo, der)

    if status == "fail" and not a.force:
        print(json.dumps({"status": status, "failed": [c for c in checks if not c["ok"]]}, indent=2))
        sys.exit(2)

    stem = re.sub(r"[^A-Za-z0-9]+", "-", memo["deal"].get("name", "deal")).strip("-") + "-IC-Memo"
    formats = {f.strip().lower() for f in a.formats.split(",")}
    outputs = []
    html_path = out / f"{stem}.html"
    html_path.write_text(build_html(memo, brand, der, status, placeholders), encoding="utf-8")
    if "html" in formats:
        outputs.append(str(html_path))
    if "pdf" in formats:
        engine = write_pdf(html_path, out / f"{stem}.pdf", one_page=memo.get("variant", "one_pager") == "one_pager")
        if engine:
            outputs.append(str(out / f"{stem}.pdf"))
        else:
            outputs.append(f"PDF not written: no PDF engine (playwright or weasyprint). HTML kept at {html_path}")
    if "docx" in formats:
        write_docx(memo, brand, der, out / f"{stem}.docx")
        outputs.append(str(out / f"{stem}.docx"))
    summary = run_summary(memo, status, checks, placeholders, outputs)
    (out / f"{stem}-run-summary.md").write_text(summary)
    print(json.dumps({"status": status, "outputs": outputs, "placeholders": placeholders,
                      "failed": [c for c in checks if not c["ok"]]}, indent=2))


if __name__ == "__main__":
    main()
