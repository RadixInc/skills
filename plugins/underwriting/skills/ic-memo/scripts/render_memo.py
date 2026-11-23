#!/usr/bin/env python3
"""Render an IC memo from a memo JSON (radix.ic_memo/v2) and a brand profile JSON.

The agent gathers the data and writes memo.json (see references/memo-schema.md).
This script does everything that must look and compute the same on every run:
derived figures, the risk-flag rules, the accuracy gate, layout, and export to HTML, PDF and Word.

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

# Fixed design. Only the brand colors, logo and firm text change with the brand profile.
NEUTRAL = {
    "ink": "#181d27", "strong": "#252b37", "muted": "#414651", "faint": "#717680", "hush": "#a4a7ae",
    "rule": "#eaeaf0", "rule_strong": "#d5d7da", "panel": "#f7f8fb",
    "warn": "#b54708", "warn_bg": "#fffaeb", "good": "#067647", "bad": "#b42318",
}
APPROVED_FONTS = {"Manrope"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

REV_GROUPS = [("potential_rent", "Potential rent"), ("loss_to_lease", "Loss to lease"),
              ("vacancy_credit", "Vacancy and credit loss"), ("other_income", "Other income")]
EXP_GROUPS = [("controllable", "Controllable expenses"), ("utilities", "Utilities"),
              ("taxes_insurance", "Taxes and insurance"), ("management", "Management fee")]


# ---------- formatting ----------

def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt_money(v, dp=0):
    if not is_num(v):
        return "-"
    s = f"{abs(v):,.{dp}f}"
    return f"(${s})" if v < 0 else f"${s}"


def fmt_compact(v):
    """$3.24M, $958K, $983."""
    if not is_num(v):
        return "-"
    a, sign = abs(v), "-" if v < 0 else ""
    if a >= 1e6:
        return f"{sign}${a / 1e6:.2f}M"
    if a >= 1e4:
        return f"{sign}${a / 1e3:.0f}K"
    return f"{sign}${a:,.0f}"


def fmt_pct(v, dp=1):
    """v is a percent number (76.4 means 76.4%)."""
    return "-" if not is_num(v) else f"{v:.{dp}f}%"


def fmt_ratio(v, dp=1):
    """v is a ratio (0.0525 means 5.25% with dp=2)."""
    return "-" if not is_num(v) else f"{v * 100:.{dp}f}%"


def fmt_int(v):
    return "-" if not is_num(v) else f"{v:,.0f}"


def fmt_mult(v):
    return "-" if not is_num(v) else f"{v:.2f}x"


def fmt_signed_pct(v, dp=1):
    return "-" if not is_num(v) else f"{v * 100:+.{dp}f}%"


def date_label(d, short=False):
    try:
        dt = datetime.strptime(str(d)[:10], "%Y-%m-%d")
        return f"{MONTHS[dt.month - 1]} {dt.year}" if short else f"{MONTHS[dt.month - 1]} {dt.day}, {dt.year}"
    except Exception:
        return str(d or "")


def esc(s):
    return html.escape("" if s is None else str(s))


# ---------- color ----------

def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _lum(h):
    c = [x / 255 for x in _rgb(h)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a, b, t):
    """t=0 -> a, t=1 -> b."""
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ra, rb))


def valid_hex(c):
    return isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) is not None


# ---------- derived figures ----------

def group_sum(lines, group, col):
    vals = [l["values"].get(col) for l in lines if l.get("group") == group]
    vals = [v for v in vals if is_num(v)]
    return sum(vals) if vals else None


def unit_type(r):
    """Unit mix rows are by bed / bath (groupBy unitMixBath). Older files may carry only a label."""
    if is_num(r.get("beds")) and is_num(r.get("baths")):
        b = r["baths"]
        baths = str(int(b)) if float(b).is_integer() else f"{b:.1f}"
        return f'{"Studio" if r["beds"] == 0 else str(int(r["beds"])) + " bed"} / {baths} bath'
    return r.get("label", "")


def derive(memo):
    """Every derived figure, once. Arithmetic on inputs only; nothing estimated."""
    d = {}
    deal, act = memo.get("deal", {}), memo.get("actuals") or {}
    units = deal.get("units")
    cols = [c["key"] for c in act.get("columns", [])]
    terms = memo.get("deal_terms") or {}
    price = terms.get("price")
    noi = act.get("noi") or {}
    d["price_per_unit"] = price / units if is_num(price) and is_num(units) and units else None
    d["cap"] = {k: (noi[k] / price if is_num(noi.get(k)) and is_num(price) and price else None) for k in cols}
    d["noi_per_unit"] = {k: (noi[k] / units if is_num(noi.get(k)) and units else None) for k in cols}
    lines = act.get("revenue", []) + act.get("expenses", [])
    d["groups"] = {g: {k: group_sum(lines, g, k) for k in cols} for g, _ in REV_GROUPS + EXP_GROUPS}
    pf = memo.get("proforma") or {}
    d["pf_delta"] = {}
    for key in ("egr", "opex", "noi"):
        a, p = (act.get(key) or {}).get("T12"), pf.get(key)
        d["pf_delta"][key] = (p - a) / abs(a) if is_num(a) and is_num(p) and a else None
    for g, _ in REV_GROUPS + EXP_GROUPS:
        a, p = d["groups"][g].get("T12"), (pf.get("groups") or {}).get(g)
        d["pf_delta"][g] = (p - a) / abs(a) if is_num(a) and is_num(p) and a else None
    su = memo.get("sources_uses") or {}
    eq_layers = [l["amount"] for l in (memo.get("capital_stack") or {}).get("layers", []) if l.get("kind") == "equity" and is_num(l.get("amount"))]
    d["required_equity"] = terms.get("required_equity") if is_num(terms.get("required_equity")) else (sum(eq_layers) if eq_layers else None)
    d["uses_total"] = sum(u["amount"] for u in su.get("uses", []) if is_num(u.get("amount"))) if su.get("uses") else None
    d["sources_total"] = sum(s["amount"] for s in su.get("sources", []) if is_num(s.get("amount"))) if su.get("sources") else None
    # Actual lines whose T3 annualized differs from T12 by 15% or more (same sign, in magnitude).
    d["hot_lines"] = []
    if "T12" in cols and "T3" in cols:
        for section in ("revenue", "expenses"):
            for row in act.get(section, []):
                a, b = row["values"].get("T12"), row["values"].get("T3")
                if is_num(a) and is_num(b) and abs(a) >= 10000 and (a > 0) == (b > 0):
                    chg = (abs(b) - abs(a)) / abs(a)
                    if abs(chg) >= 0.15:
                        d["hot_lines"].append({"section": section, "label": row["label"], "chg": chg})
    d["flags"] = risk_flags(memo, d)
    return d


# ---------- pre-send checks (fixed rules, documented in references/pre-send-checks.md; not printed on the memo) ----------

def risk_flags(memo, d):
    act, pf, snap = memo.get("actuals") or {}, memo.get("proforma") or {}, memo.get("snapshot") or {}
    units = (memo.get("deal") or {}).get("units")
    ret, hcf = memo.get("returns") or {}, memo.get("hold_cash_flow") or {}
    rules = []

    def rule(name, test, fired, observed):
        rules.append({"name": name, "test": test, "fired": bool(fired), "observed": observed})

    egr_d, noi_d = d["pf_delta"].get("egr"), d["pf_delta"].get("noi")
    if is_num(egr_d):
        rule("Pro forma revenue well above actual", "Y1 EGR vs T12 EGR > +10%", egr_d > 0.10,
             f"{fmt_compact(act['egr']['T12'])} to {fmt_compact(pf['egr'])} ({fmt_signed_pct(egr_d)})")
    if is_num(noi_d):
        rule("Pro forma NOI well above actual", "Y1 NOI vs T12 NOI > +15%", noi_d > 0.15,
             f"{fmt_compact(act['noi']['T12'])} to {fmt_compact(pf['noi'])} ({fmt_signed_pct(noi_d)})")
    oi_a, oi_p = d["groups"]["other_income"].get("T12"), (pf.get("groups") or {}).get("other_income")
    if is_num(oi_a) and is_num(oi_p) and oi_a > 0:
        rule("Other income dropped in pro forma", "Y1 other income < 50% of T12", oi_p < 0.5 * oi_a,
             f"{fmt_compact(oi_a)} to {fmt_compact(oi_p)}")
    occ = snap.get("occupancy_pct")
    if is_num(occ):
        rule("Low occupancy", "Rent roll occupancy < 90%", occ < 90, f"{fmt_pct(occ)} occupied")
    exp = snap.get("leases_expiring_next90")
    if is_num(exp) and is_num(units) and units:
        rule("Near-term expirations", "Leases expiring in 90 days > 10% of units", exp / units > 0.10,
             f"{fmt_int(exp)} leases, {fmt_ratio(exp / units)} of units")
    path = hcf.get("noi") or []
    if len(path) >= 2 and all(is_num(x) for x in path):
        rule("NOI falls over the hold", "Final-year NOI < Year 1 NOI", path[-1] < path[0],
             f"{fmt_compact(path[0])} to {fmt_compact(path[-1])}")
    exit_cap, t12_cap = (ret.get("exit") or {}).get("cap"), d["cap"].get("T12")
    if is_num(exit_cap) and is_num(t12_cap):
        rule("Exit cap at or below going-in", "Exit cap <= cap rate on T12 NOI", exit_cap <= t12_cap,
             f"exit {fmt_ratio(exit_cap, 2)} vs going-in {fmt_ratio(t12_cap, 2)}")
    if "T3" in [c["key"] for c in act.get("columns", [])]:
        hot = [h for h in d["hot_lines"] if h["section"] == "expenses" and h["chg"] >= 0.25]
        top = max(hot, key=lambda h: h["chg"]) if hot else None
        rule("Expense line running hot", "Any expense line T3 ann. >= 25% above T12", bool(hot),
             (f"{top['label']} {fmt_signed_pct(top['chg'], 0)}" + (f", {len(hot) - 1} more" if len(hot) > 1 else "")) if top else "none")
    gpr, mkt = d["groups"]["potential_rent"].get("T12"), snap.get("market_rent")
    if is_num(gpr) and is_num(mkt) and is_num(units) and units and mkt:
        per = gpr / units / 12
        rule("T12 rent doesn't match the rent roll", "T12 potential rent per unit vs rent roll market rent off by > 20%",
             abs(per - mkt) / mkt > 0.20, f"{fmt_money(per)} vs {fmt_money(mkt)} per unit per month")
    dscr = [x for x in (hcf.get("dscr") or []) if is_num(x)]
    if dscr:
        rule("Thin debt coverage", "Minimum DSCR < 1.25x", min(dscr) < 1.25, f"min {min(dscr):.2f}x")
    return rules


# ---------- accuracy gate ----------

NUM_TOKEN = re.compile(r"\$?\(?-?\d[\d,]*(?:\.\d+)?\)?[%xMK]?")


class Shown:
    """Every figure the page prints, so narrative can be checked against what the reader sees."""
    def __init__(self):
        self.s = set()

    def add(self, txt):
        if txt and txt != "-":
            self.s.add(txt.strip("()"))
            self.s.add(txt.replace("(", "").replace(")", ""))
        return txt

    def money(self, v):
        if is_num(v):
            a = abs(v)
            self.add(fmt_money(a))
            self.add(fmt_compact(a))
            for unit, div in (("M", 1e6), ("K", 1e3)):
                if a >= div:
                    for dp in (0, 1, 2):
                        self.add(f"${a / div:,.{dp}f}{unit}")
        return fmt_money(v)


def run_gate(memo, der, shown):
    checks, placeholders = [], []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    deal, act = memo.get("deal", {}), memo.get("actuals") or {}
    for c in act.get("columns", []):
        k = c["key"]
        rev = sum(r["values"].get(k) or 0 for r in act.get("revenue", []))
        exp = sum(r["values"].get(k) or 0 for r in act.get("expenses", []))
        egr, opex, noi = (act.get("egr") or {}).get(k), (act.get("opex") or {}).get(k), (act.get("noi") or {}).get(k)
        if is_num(egr):
            check(f"Actual {k}: revenue lines sum to EGR", abs(rev - egr) <= TOL, f"{rev:,.2f} vs {egr:,.2f}")
        if is_num(opex):
            check(f"Actual {k}: expense lines sum to OpEx", abs(exp - opex) <= TOL, f"{exp:,.2f} vs {opex:,.2f}")
        if all(is_num(x) for x in (egr, opex, noi)):
            check(f"Actual {k}: NOI = EGR - OpEx", abs(egr - opex - noi) <= TOL, f"{egr - opex:,.2f} vs {noi:,.2f}")
    missing = [r["label"] for r in act.get("revenue", []) + act.get("expenses", []) if not r.get("group")]
    check("Every actual line has a group", not missing, ", ".join(missing))

    pf = memo.get("proforma")
    if pf:
        g = pf.get("groups") or {}
        rev = sum(g.get(k) or 0 for k, _ in REV_GROUPS)
        exp = sum(g.get(k) or 0 for k, _ in EXP_GROUPS)
        check("Pro forma: revenue groups sum to EGR", abs(rev - pf.get("egr", 0)) <= TOL, f"{rev:,.2f} vs {pf.get('egr', 0):,.2f}")
        check("Pro forma: expense groups sum to OpEx", abs(exp - pf.get("opex", 0)) <= TOL, f"{exp:,.2f} vs {pf.get('opex', 0):,.2f}")
        check("Pro forma: NOI = EGR - OpEx", abs(pf.get("egr", 0) - pf.get("opex", 0) - pf.get("noi", 0)) <= TOL)
        hn = (memo.get("hold_cash_flow") or {}).get("noi") or []
        if hn:
            check("Pro forma Y1 NOI matches hold cash flow Y1", abs(hn[0] - pf.get("noi", 0)) <= TOL, f"{hn[0]:,.2f} vs {pf.get('noi', 0):,.2f}")
    hcf = memo.get("hold_cash_flow") or {}
    if hcf.get("noi") and hcf.get("net_cash_flow"):
        n = len(hcf["noi"])
        ds, cx = hcf.get("debt_service") or [0] * n, hcf.get("capex") or [0] * n
        bad = [i + 1 for i in range(n) if abs(hcf["noi"][i] - (ds[i] or 0) - (cx[i] or 0) - hcf["net_cash_flow"][i]) > TOL]
        check("Hold cash flow: net = NOI - debt service - capex", not bad, f"years {bad}")
    if is_num(der.get("uses_total")) and is_num(der.get("sources_total")):
        check("Sources equal uses", abs(der["uses_total"] - der["sources_total"]) <= TOL, f"{der['sources_total']:,.2f} vs {der['uses_total']:,.2f}")
    cs = memo.get("capital_stack") or {}
    if cs.get("layers") and is_num(der.get("sources_total")):
        tot = sum(l["amount"] for l in cs["layers"])
        check("Capital stack equals total sources", abs(tot - der["sources_total"]) <= TOL, f"{tot:,.2f} vs {der['sources_total']:,.2f}")
    req = der.get("required_equity")
    eq_layers = [l["amount"] for l in cs.get("layers", []) if l.get("kind") == "equity"]
    if is_num(req) and eq_layers:
        check("Required equity equals the equity in the capital stack", abs(req - sum(eq_layers)) <= TOL, f"{req:,.2f} vs {sum(eq_layers):,.2f}")
    wf = memo.get("waterfall") or {}
    if wf.get("partners"):
        pe = sum(x.get("equity") or 0 for x in wf["partners"])
        if is_num(req):
            check("Waterfall partner equity adds to required equity", abs(pe - req) <= TOL, f"{pe:,.2f} vs {req:,.2f}")
        for x in wf["partners"]:
            if all(is_num(x.get(k)) for k in ("equity", "distributions", "profit")):
                check(f"Waterfall {x['label']}: profit = distributions - equity", abs(x["distributions"] - x["equity"] - x["profit"]) <= TOL)
        lp_ = (memo.get("returns") or {}).get("levered") or {}
        if is_num(lp_.get("profit")):
            pp = sum(x.get("profit") or 0 for x in wf["partners"])
            check("Waterfall profit adds to levered deal profit", abs(pp - lp_["profit"]) <= TOL, f"{pp:,.2f} vs {lp_['profit']:,.2f}")
        for t in wf.get("tiers", []):
            if is_num(t.get("lp")) and is_num(t.get("gp")):
                check(f"Waterfall {t['label']}: splits add to 100%", abs(t["lp"] + t["gp"] - 1) < 1e-6)
    um = memo.get("unit_mix") or {}
    if um.get("rows"):
        ru = sum(r.get("units") or 0 for r in um["rows"])
        check("Unit mix adds to the deal unit count", ru == deal.get("units"), f"{ru} vs {deal.get('units')}")
    snap = memo.get("snapshot") or {}
    if is_num(snap.get("occupancy_pct")) and is_num((um.get("total") or {}).get("occupied_pct")):
        check("Snapshot occupancy matches the rent roll total", abs(snap["occupancy_pct"] - um["total"]["occupied_pct"]) < 0.05)
    src = memo.get("sources") or {}
    check("Rent roll as-of date is stated", bool((src.get("rent_roll") or {}).get("as_of")))
    check("Actual column windows are stated", all(c.get("window") for c in act.get("columns", [])))
    if any(memo.get(k) for k in ("proforma", "returns", "capital_stack", "sources_uses", "sensitivity", "hold_cash_flow")):
        check("Client model file is named", bool((src.get("client_model") or {}).get("file")))

    for name, text in [("Summary", (memo.get("commentary") or {}).get("text") or "")] + \
                      [(f"Note on {k}", n) for k, n in ((memo.get("proforma") or {}).get("notes") or {}).items() if n]:
        unmatched = []
        for tok in NUM_TOKEN.findall(text):
            t = tok.strip().rstrip(".,;:")
            bare = t.strip("()")
            if re.fullmatch(r"\d{1,2}", bare) or re.fullmatch(r"(19|20)\d\d", bare):
                continue
            if bare not in shown.s:
                unmatched.append(t)
        check(f"{name}: every figure appears on the page", not unmatched, ", ".join(unmatched))

    for key, label in (("deal_terms", "Price"), ("returns", "Returns"), ("proforma", "Pro forma"),
                       ("capital_stack", "Capital stack"), ("sources_uses", "Sources and uses"),
                       ("sensitivity", "Sensitivity"), ("hold_cash_flow", "Hold-period cash flow")):
        b = memo.get(key)
        if not b or (key == "deal_terms" and not is_num(b.get("price"))):
            placeholders.append(f"{label}. Source: client model.")
    if not (memo.get("commentary") or {}).get("text"):
        placeholders.append("Summary.")
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
            css.append(f"@font-face{{font-family:'Manrope';font-weight:{w};src:url(data:font/woff2;base64,{b64}) format('woff2');}}")
    return "\n".join(css)


def ph(label, source="client model"):
    return f'<div class="rx-alert"><b>Needs {esc(source)}</b><span>{esc(label)}</span></div>'


def noi_chart(t12, years, noi, coc, bar, w=560, h=132):
    """NOI by year from the model, with the T12 actual as the first, grey bar."""
    cats = (["T12"] if is_num(t12) else []) + list(years)
    vals = ([t12] if is_num(t12) else []) + list(noi)
    if not vals or not all(is_num(v) for v in vals):
        return ""
    top, bottom, left, right = 16, 30, 4, 4
    vmax = max(vals) * 1.08 or 1
    slot = (w - left - right) / len(vals)
    bw = slot * 0.54
    base_y = h - bottom
    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="NOI by year">',
           f'<line x1="{left}" x2="{w - right}" y1="{base_y}" y2="{base_y}" stroke="{NEUTRAL["rule_strong"]}" stroke-width="1"/>']
    for i, (c, v) in enumerate(zip(cats, vals)):
        x = left + slot * i + (slot - bw) / 2
        bh = (v / vmax) * (base_y - top)
        actual = is_num(t12) and i == 0
        fill = NEUTRAL["hush"] if actual else bar
        out.append(f'<rect x="{x:.1f}" y="{base_y - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="{fill}"/>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{base_y - bh - 4:.1f}" text-anchor="middle" class="cv">{esc(fmt_compact(v))}</text>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{base_y + 11:.1f}" text-anchor="middle" class="cx">{esc(c)}</text>')
        sub = "actual" if actual else (fmt_ratio(coc[i - (1 if is_num(t12) else 0)]) + " CoC" if coc and is_num(coc[i - (1 if is_num(t12) else 0)]) else "")
        out.append(f'<text x="{x + bw / 2:.1f}" y="{base_y + 22:.1f}" text-anchor="middle" class="cs">{esc(sub)}</text>')
    out.append("</svg>")
    return "".join(out)


def build_html(memo, brand, der, S):
    deal, src = memo["deal"], memo.get("sources") or {}
    colors = brand.get("colors", {})
    primary = colors.get("primary") if valid_hex(colors.get("primary")) else "#144a85"
    accent = colors.get("accent") if valid_hex(colors.get("accent")) else "#1f76d6"
    tint = colors.get("accent_tint") if valid_hex(colors.get("accent_tint")) else "#eff4fe"
    font = brand.get("fonts", {}).get("body", "Manrope")
    font = font if font in APPROVED_FONTS else "Manrope"
    act, pf = memo.get("actuals") or {}, memo.get("proforma") or {}
    terms, ret = memo.get("deal_terms") or {}, memo.get("returns") or {}
    snap, units = memo.get("snapshot") or {}, deal.get("units")
    cs, su = memo.get("capital_stack") or {}, memo.get("sources_uses") or {}
    hcf, sens = memo.get("hold_cash_flow") or {}, memo.get("sensitivity") or {}
    rr = src.get("rent_roll") or {}
    has_debt = any(l.get("kind") == "debt" for l in cs.get("layers", []))
    all_cash = bool(cs.get("layers")) and not has_debt

    # ----- page head
    logo = brand.get("logo") or {}
    brand_mark = (f'<img class="logo" src="{esc(logo["data_uri"])}" alt="">' if logo.get("data_uri")
                  else f'<span class="wordmark">{esc(logo.get("wordmark_text") or brand.get("firm", {}).get("display_name") or "")}</span>')
    marks = [memo.get("status_label") or "Screening memo"]
    if memo.get("strategy"):
        marks.append(memo["strategy"])
    if all_cash:
        marks.append("All cash")
    if terms.get("hold_years"):
        marks.append(f"{terms['hold_years']}-year hold")
    facts = [deal.get("address", "")]
    if units:
        facts.append(f"{S.add(fmt_int(units))} units")
    if deal.get("year_built"):
        facts.append(f"built {deal['year_built']}")
    if deal.get("building_type"):
        facts.append(deal["building_type"])
    if deal.get("total_sf"):
        facts.append(f"{S.add(fmt_int(deal['total_sf']))} SF")
    um = memo.get("unit_mix") or {}
    mix_line = " · ".join(f"{S.add(fmt_int(r['units']))} × {esc(unit_type(r))}" for r in um.get("rows", []) if r.get("units"))
    if is_num(snap.get("occupancy_pct")):
        mix_line += f" · {S.add(fmt_pct(snap['occupancy_pct']))} occupied on the {esc(date_label(rr.get('as_of')))} rent roll"
    com = memo.get("commentary") or {}
    summary_html = ""
    if com.get("text"):
        summary_html = f'<div class="ph__summary"><p>{esc(com["text"])}</p></div>'

    # ----- deal metrics (rx-metric-tile grid)
    lev, unl, ex = ret.get("levered") or {}, ret.get("unlevered") or {}, ret.get("exit") or {}

    def tile(label, value, comparison=""):
        return (f'<div class="rx-metric-tile"><p class="rx-metric-tile__label">{esc(label)}</p>'
                f'<div class="rx-metric-tile__row"><p class="rx-metric-tile__value">{esc(value)}</p></div>'
                f'<p class="rx-metric-tile__comparison">{esc(comparison)}</p></div>')
    S.money(terms.get("price")); S.money(der["price_per_unit"]); S.money(lev.get("profit")); S.money(ex.get("gross_proceeds"))
    dscr = [x for x in (hcf.get("dscr") or []) if is_num(x)]
    t12_cap = der["cap"].get("T12")
    req = der.get("required_equity")
    debt = sum(l["amount"] for l in cs.get("layers", []) if l.get("kind") == "debt" and is_num(l.get("amount")))
    wf = memo.get("waterfall") or {}
    lp = next((x for x in wf.get("partners", []) if x.get("role") == "lp"), None)
    hero_bits = []
    if is_num(terms.get("price")):
        hero_bits.append(f"Purchase price {S.add(fmt_compact(terms['price']))} ({S.money(der['price_per_unit'])} per unit)")
    if debt:
        hero_bits.append(f"loan {S.add(fmt_compact(debt))}")
        S.money(debt)
    elif all_cash:
        hero_bits.append("all cash")
    if is_num(req) and is_num(units) and units:
        hero_bits.append(f"{S.money(req / units)} per unit")
    S.money(req)
    hero = (f'<div class="rx-metric-tile rx-metric-tile--hero"><p class="rx-metric-tile__label">Required equity</p>'
            f'<div class="rx-metric-tile__row"><p class="rx-metric-tile__value">{esc(S.add(fmt_compact(req)))}</p></div>'
            f'<p class="rx-metric-tile__comparison">{esc(" · ".join(hero_bits))}</p></div>') if is_num(req) else ""
    irr_cmp = f"Unlevered {S.add(fmt_ratio(unl.get('irr')))}" if unl else ""
    if lp and is_num(lp.get("irr")):
        irr_cmp = f"LP net {S.add(fmt_ratio(lp['irr']))} · " + irr_cmp
    mult_cmp = " · ".join(x for x in (f"Profit {S.add(fmt_compact(lev.get('profit')))}" if is_num(lev.get("profit")) else "",
                                      f"avg CoC {S.add(fmt_ratio(lev.get('avg_coc')))}" if is_num(lev.get("avg_coc")) else "") if x)
    tiles = [
        hero,
        tile("Levered IRR", S.add(fmt_ratio(lev.get("irr"))), irr_cmp),
        tile("Equity multiple", S.add(fmt_mult(lev.get("moic"))), mult_cmp),
        tile("Going-in cap", S.add(fmt_ratio(terms.get("going_in_cap_model"), 2)),
             (f"Pro forma NOI · exit {S.add(fmt_ratio(ex.get('cap'), 2))} in Y{terms.get('hold_years')}" if dscr and is_num(ex.get("cap"))
              else f"Pro forma NOI · {S.add(fmt_ratio(t12_cap, 2))} on T12" if is_num(t12_cap) else "Pro forma NOI")),
        tile("Min DSCR", S.add(fmt_mult(min(dscr))), "Lowest year of the hold") if dscr else
        tile("Exit cap", S.add(fmt_ratio(ex.get("cap"), 2)),
             f"{S.add(fmt_compact(ex.get('gross_proceeds')))} sale in Y{terms.get('hold_years')}" if is_num(ex.get("gross_proceeds")) else ""),
    ]
    metrics_html = f'<div class="mt-grid">{"".join(tiles)}</div>' if ret or is_num(terms.get("price")) else ph("IRR, multiple, cash-on-cash, price, going-in and exit cap")

    # ----- NOI over the hold
    if hcf.get("noi"):
        years = hcf.get("years") or [f"Y{i + 1}" for i in range(len(hcf["noi"]))]
        for v in hcf["noi"]:
            S.money(v)
        chart = noi_chart((act.get("noi") or {}).get("T12"), years, hcf["noi"], hcf.get("coc") or [], primary)
        rows = []

        def hrow(label, vals, f, cls=""):
            return (f'<tr class="rx-rtbl__tr{cls}"><th scope="row" class="rx-rtbl__rowlabel">{esc(label)}</th>' +
                    "".join(f'<td class="rx-rtbl__td rx-rtbl__td--num">{esc(f(v))}</td>' for v in vals) + "</tr>")
        cm = lambda v: S.add(fmt_compact(v)) if is_num(v) else "-"
        neg = lambda v: f"({S.add(fmt_compact(abs(v)))})" if is_num(v) and v else "-"
        if hcf.get("egr"):
            rows.append(hrow("EGR", hcf["egr"], cm))
        if hcf.get("opex"):
            rows.append(hrow("OpEx", hcf["opex"], neg))
        if has_debt and hcf.get("debt_service"):
            rows.append(hrow("Debt service", hcf["debt_service"], neg))
        if any(is_num(v) and v for v in hcf.get("capex") or []):
            rows.append(hrow("Capital expenditures", hcf["capex"], neg))
        if hcf.get("net_cash_flow"):
            for v in hcf["net_cash_flow"]:
                S.money(v)
            rows.append(hrow("Net cash flow", hcf["net_cash_flow"], cm, " rx-rtbl__tr--strong"))
        if dscr:
            rows.append(hrow("DSCR", hcf["dscr"], lambda v: S.add(fmt_mult(v))))
        for v in hcf.get("coc") or []:
            S.add(fmt_ratio(v))
        head = "".join(f'<th class="rx-rtbl__th rx-rtbl__th--num">{esc(y)}</th>' for y in years)
        legend = (f'<span class="rxt__pill"><span class="rxt__swatch" style="background:{NEUTRAL["hush"]}"></span>T12 actual</span>'
                  f'<span class="rxt__pill"><span class="rxt__swatch" style="background:{primary}"></span>Pro forma</span>')
        hold_html = (f'<div class="rxt__legend">{legend}</div>{chart}'
                     f'<div class="rx-rtbl rx-rtbl--dense"><table class="rx-rtbl__table"><colgroup><col style="width:20%">' + "<col>" * len(years) +
                     f'</colgroup><thead><tr><th class="rx-rtbl__th rx-rtbl__th--pinned">$ per year</th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
                     + ('<p class="rx-chart-note">No debt in the model, so net cash flow equals NOI.</p>' if not has_debt else ""))
    else:
        hold_html = ph("NOI, debt service, net cash flow and cash-on-cash by year")

    # ----- capitalization
    if su.get("uses"):
        def su_rows(title, items, total):
            out = f'<tr class="rx-rtbl__group"><th class="rx-rtbl__grouptitle" colspan="3">{esc(title)}</th></tr>'
            for it in items:
                out += (f'<tr class="rx-rtbl__tr"><th scope="row" class="rx-rtbl__rowlabel">{esc(it["label"])}</th>'
                        f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.money(it["amount"])}</td>'
                        f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.add(fmt_ratio(it["amount"] / total))}</td></tr>')
            return out + (f'<tr class="rx-rtbl__tr rx-rtbl__tr--total"><th scope="row" class="rx-rtbl__rowlabel">Total {esc(title.lower())}</th>'
                          f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.money(total)}</td><td class="rx-rtbl__td rx-rtbl__td--num">100%</td></tr>')
        cap_html = (f'<div class="rx-rtbl"><table class="rx-rtbl__table"><colgroup><col style="width:50%"><col><col style="width:18%"></colgroup>'
                    f'<thead><tr><th class="rx-rtbl__th rx-rtbl__th--pinned">At closing</th><th class="rx-rtbl__th rx-rtbl__th--num">$</th>'
                    f'<th class="rx-rtbl__th rx-rtbl__th--num">%</th></tr></thead><tbody>{su_rows("Uses", su["uses"], der["uses_total"])}'
                    f'{su_rows("Sources", su["sources"], der["sources_total"])}</tbody></table></div>')
        if cs.get("terms"):
            cap_html += '<div class="rx-detail-list">' + "".join(f'<div class="rx-detail-list__row"><span class="rx-detail-list__label">{esc(t)}</span></div>' for t in cs["terms"]) + "</div>"
        for l in cs.get("layers", []):
            S.money(l["amount"])
    else:
        cap_html = ph("Sources and uses, debt terms")

    # ----- sensitivity (report table, base row and column highlighted)
    if sens.get("values"):
        base = sens.get("base") or {}
        pct = sens.get("format", "pct") == "pct"
        head = "".join(f'<th class="rx-rtbl__th rx-rtbl__th--num{" rx-rtbl__th--subject" if c == base.get("col") else ""}">{esc(c)}</th>' for c in sens["cols"])
        body = ""
        for rl, rv in zip(sens["rows"], sens["values"]):
            is_row = rl == base.get("row")
            body += f'<tr class="rx-rtbl__tr{" rx-rtbl__tr--subject" if is_row else ""}"><th scope="row" class="rx-rtbl__rowlabel">{esc(rl)}</th>'
            for c, v in zip(sens["cols"], rv):
                txt = S.add(fmt_ratio(v)) if pct else S.add(fmt_mult(v))
                cls = " rx-rtbl__td--subject" if c == base.get("col") else ""
                cls += " is-base" if is_row and c == base.get("col") else ""
                body += f'<td class="rx-rtbl__td rx-rtbl__td--num{cls}">{esc(txt)}</td>'
            body += "</tr>"
        sens_html = (f'<div class="rx-rtbl"><table class="rx-rtbl__table"><thead><tr><th class="rx-rtbl__th rx-rtbl__th--pinned">'
                     f'{esc(sens.get("row_label", ""))}</th>{head}</tr></thead><tbody>{body}</tbody></table></div>'
                     f'<p class="rx-chart-note">{esc(sens.get("title", ""))}. Base case in bold.</p>')
    else:
        sens_html = ph("IRR by exit cap rate and hold period")

    # ----- equity waterfall (optional)
    wf_opt = memo.get("waterfall_option", "auto")  # auto: show when the model has one; always; never
    wf_html = ""
    if wf_opt == "always" and not wf.get("partners"):
        wf_html = f'<div class="grid"><section class="card"><div class="card__head"><span class="card__title">Equity waterfall</span></div>{ph("LP and GP splits by tier, and returns by partner")}</section></div>'
    if wf_opt != "never" and wf.get("partners"):
        tier_rows = "".join(
            f'<tr class="rx-rtbl__tr"><th scope="row" class="rx-rtbl__rowlabel">{esc(t["label"])}</th><td class="rx-rtbl__td">{esc(t.get("hurdle", ""))}</td>'
            f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.add(fmt_ratio(t.get("lp"), 0))}</td><td class="rx-rtbl__td rx-rtbl__td--num">{S.add(fmt_ratio(t.get("gp"), 0))}</td></tr>'
            for t in wf.get("tiers", []))
        tiers_html = (f'<div class="rx-rtbl rx-rtbl--dense"><table class="rx-rtbl__table"><colgroup><col style="width:36%"><col><col style="width:13%"><col style="width:13%"></colgroup>'
                      f'<thead><tr><th class="rx-rtbl__th rx-rtbl__th--pinned">Tier</th><th class="rx-rtbl__th">Hurdle</th><th class="rx-rtbl__th rx-rtbl__th--num">LP</th>'
                      f'<th class="rx-rtbl__th rx-rtbl__th--num">GP</th></tr></thead><tbody>{tier_rows}</tbody></table></div>')
        def prow(x, cls=""):
            for k in ("equity", "distributions", "profit", "promote"):
                S.money(x.get(k))
            return (f'<tr class="rx-rtbl__tr{cls}"><th scope="row" class="rx-rtbl__rowlabel">{esc(x["label"])}</th>'
                    f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.add(fmt_compact(x.get("equity")))}</td>'
                    f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.add(fmt_compact(x.get("distributions")))}</td>'
                    f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.add(fmt_compact(x.get("profit")))}</td>'
                    f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.add(fmt_ratio(x.get("irr")))}</td>'
                    f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.add(fmt_mult(x.get("moic")))}</td>'
                    f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.add(fmt_compact(x.get("promote"))) if is_num(x.get("promote")) and x.get("promote") else "-"}</td></tr>')
        parts = wf["partners"]
        tot = {"label": "Total", "equity": sum(x.get("equity") or 0 for x in parts), "distributions": sum(x.get("distributions") or 0 for x in parts),
               "profit": sum(x.get("profit") or 0 for x in parts), "irr": lev.get("irr"), "moic": lev.get("moic"), "promote": None}
        partners_html = (f'<div class="rx-rtbl rx-rtbl--dense"><table class="rx-rtbl__table"><colgroup><col style="width:22%"><col><col><col><col><col><col></colgroup>'
                         f'<thead><tr><th class="rx-rtbl__th rx-rtbl__th--pinned">Partner</th><th class="rx-rtbl__th rx-rtbl__th--num">Equity</th>'
                         f'<th class="rx-rtbl__th rx-rtbl__th--num">Distributions</th><th class="rx-rtbl__th rx-rtbl__th--num">Profit</th>'
                         f'<th class="rx-rtbl__th rx-rtbl__th--num">IRR</th><th class="rx-rtbl__th rx-rtbl__th--num">Multiple</th>'
                         f'<th class="rx-rtbl__th rx-rtbl__th--num">Promote</th></tr></thead><tbody>'
                         + "".join(prow(x) for x in parts) + prow(tot, " rx-rtbl__tr--total rx-rtbl__tr--total-first") + "</tbody></table></div>")
        wf_html = (f'<div class="grid"><section class="card"><div class="card__head"><span class="card__title">Equity waterfall</span>'
                   f'<span class="card__meta">{esc(wf.get("structure", ""))}</span></div><div class="wf">{tiers_html}{partners_html}</div></section></div>')

    # ----- operating statement (report table; pro forma is the subject column)
    cols = act.get("columns", [])
    has_pf = bool(pf)
    notes = {k: v for k, v in (pf.get("notes") or {}).items() if v}
    has_notes = bool(notes)
    ncol = len(cols) + 1 + (2 if has_pf else 0) + (1 if has_notes else 0)
    head = "".join(f'<th class="rx-rtbl__th rx-rtbl__th--num">{esc(c["label"])}</th>' for c in cols)
    if has_pf:
        head += f'<th class="rx-rtbl__th rx-rtbl__th--num rx-rtbl__th--subject">{esc(pf.get("label", "Y1 pro forma"))}</th><th class="rx-rtbl__th rx-rtbl__th--num">Change</th>'
    if has_notes:
        head += '<th class="rx-rtbl__th">Notes</th>'

    def note_td(key):
        return f'<td class="rx-rtbl__td rx-rtbl__td--note">{esc(notes.get(key, ""))}</td>' if has_notes else ""

    def change_txt(p, a):
        if not (is_num(p) and is_num(a)):
            return "-"
        c = p - a
        S.money(c)
        return S.add(("+" if c > 0 else "-" if c < 0 else "") + fmt_compact(abs(c))) if abs(c) >= 1 else "$0"

    def orow(key, label, cls=""):
        if key in ("egr", "opex", "noi"):
            vals, p = [(act.get(key) or {}).get(c["key"]) for c in cols], pf.get(key)
        else:
            vals, p = [der["groups"][key].get(c["key"]) for c in cols], (pf.get("groups") or {}).get(key)
        tds = "".join(f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.money(v)}</td>' for v in vals)
        if has_pf:
            a12 = (act.get(key) or {}).get("T12") if key in ("egr", "opex", "noi") else der["groups"][key].get("T12")
            tds += f'<td class="rx-rtbl__td rx-rtbl__td--num rx-rtbl__td--subject">{S.money(p)}</td><td class="rx-rtbl__td rx-rtbl__td--num">{change_txt(p, a12)}</td>'
        return f'<tr class="rx-rtbl__tr{cls}"><th scope="row" class="rx-rtbl__rowlabel">{esc(label)}</th>{tds}{note_td(key)}</tr>'

    def grp(title):
        return f'<tr class="rx-rtbl__group"><th class="rx-rtbl__grouptitle" colspan="{ncol}">{esc(title)}</th></tr>'

    def single(label, actual_txt, pf_txt, change="", key=""):
        blanks = "".join('<td class="rx-rtbl__td"></td>' for _ in cols[1:])
        tds = f'<td class="rx-rtbl__td rx-rtbl__td--num">{esc(actual_txt)}</td>{blanks}'
        if has_pf:
            tds += f'<td class="rx-rtbl__td rx-rtbl__td--num rx-rtbl__td--subject">{esc(pf_txt)}</td><td class="rx-rtbl__td rx-rtbl__td--num">{esc(change)}</td>'
        return f'<tr class="rx-rtbl__tr"><th scope="row" class="rx-rtbl__rowlabel">{esc(label)}</th>{tds}{note_td(key)}</tr>'
    body = grp("Revenue") + "".join(orow(k, l) for k, l in REV_GROUPS) + orow("egr", "Effective gross revenue", " rx-rtbl__tr--total rx-rtbl__tr--total-first")
    body += grp("Operating expenses") + "".join(orow(k, l) for k, l in EXP_GROUPS) + orow("opex", "Total operating expenses", " rx-rtbl__tr--total rx-rtbl__tr--total-first")
    body += orow("noi", "Net operating income", " rx-rtbl__tr--strong rx-rtbl__tr--noi")
    ops_extra = ""
    if is_num(snap.get("in_place_rent")):
        r_pf = pf.get("effective_rent")
        ops_extra += single("Rent / unit / mo (rent roll)", S.money(snap["in_place_rent"]), S.money(r_pf) if is_num(r_pf) else "-",
                            change_txt(r_pf, snap["in_place_rent"]) if is_num(r_pf) else "", "rent")
    if is_num(snap.get("occupancy_pct")):
        o_pf = pf.get("physical_occupancy")
        d_o = f"{o_pf * 100 - snap['occupancy_pct']:+.1f} pts" if is_num(o_pf) else ""
        S.add(d_o)
        ops_extra += single("Occupancy (rent roll)", S.add(fmt_pct(snap["occupancy_pct"])), S.add(fmt_ratio(o_pf)) if is_num(o_pf) else "-", d_o, "occupancy")
    if is_num(terms.get("price")):
        caps = "".join(f'<td class="rx-rtbl__td rx-rtbl__td--num">{S.add(fmt_ratio(der["cap"].get(c["key"]), 2))}</td>' for c in cols)
        if has_pf:
            pf_cap = pf["noi"] / terms["price"] if is_num(pf.get("noi")) else None
            caps += f'<td class="rx-rtbl__td rx-rtbl__td--num rx-rtbl__td--subject">{S.add(fmt_ratio(pf_cap, 2))}</td><td class="rx-rtbl__td"></td>'
        ops_extra += f'<tr class="rx-rtbl__tr"><th scope="row" class="rx-rtbl__rowlabel">Cap rate on purchase price</th>{caps}{note_td("cap_rate")}</tr>'
    if ops_extra:
        body += grp("Operations and pricing") + ops_extra
    windows = "; ".join(f'{c["label"]} {c["window"]}' for c in cols if c.get("window"))
    num_cols = ncol - 1 - (1 if has_notes else 0)
    ops_html = (f'<div class="rx-rtbl rx-rtbl--dense"><table class="rx-rtbl__table"><colgroup><col style="width:{18 if has_notes else 24}%">' + "<col>" * num_cols +
                ('<col style="width:28%">' if has_notes else "") +
                f'</colgroup><thead><tr><th class="rx-rtbl__th rx-rtbl__th--pinned">$ annual</th>{head}</tr></thead><tbody>{body}</tbody></table></div>'
                f'<p class="rx-chart-note">{esc(windows)}.</p>')

    css = f"""
{font_face_css()}
@page {{ size: Letter; margin: 0; }}
* {{ box-sizing: border-box; }}
html {{ background:#f5f5fa; }}
body {{ margin:0; padding:0.36in 0.4in 0.3in; background:#f5f5fa; font-family:'{font}', Arial, sans-serif; color:#181d27;
       font-size:7.2pt; line-height:1.4; -webkit-print-color-adjust:exact; print-color-adjust:exact; font-variant-numeric:tabular-nums; }}
p {{ margin:0; }}
.card {{ background:#fff; border:1px solid rgba(112,115,147,.11); border-radius:12px; padding:10px 12px; break-inside:avoid; }}
.card__head {{ display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; }}
.card__title {{ font-size:8.2pt; font-weight:600; color:#181d27; }}
.card__meta {{ font-size:6.4pt; font-weight:500; color:#a4a7ae; }}
.rx-rtbl--dense .rx-rtbl__table {{ font-size:6.5pt; }}
.rx-rtbl--dense th, .rx-rtbl--dense td {{ padding:0 4px; }}
.rx-rtbl td.rx-rtbl__td--num {{ overflow:visible; text-overflow:clip; }}
.ph {{ background:#fff; border:1px solid rgba(112,115,147,.11); border-radius:16px; padding:14px 16px 12px; }}
.ph__titlerow {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }}
.ph__identity {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
.ph__title {{ margin:0; font-size:17pt; font-weight:700; color:#252b37; letter-spacing:-0.01em; }}
.ph__aside {{ text-align:right; }}
.wordmark {{ font-weight:800; font-size:12pt; letter-spacing:-0.02em; color:{primary}; }}
.logo {{ max-height:20px; max-width:130px; }}
.ph__date {{ font-size:6.6pt; color:#717680; font-weight:500; margin-top:2px; }}
.ph__facts {{ margin-top:5px; font-size:7pt; color:#414651; font-weight:500; }}
.ph__mix {{ margin-top:1px; font-size:7pt; color:#717680; font-weight:500; }}
.ph__summary {{ display:flex; gap:8px; align-items:flex-start; margin-top:9px; padding-top:9px; border-top:1px solid #eaeaf0; }}
.ph__summary p {{ font-size:7.8pt; line-height:1.5; color:#181d27; }}
.grid {{ display:grid; gap:10px; margin-top:10px; }}
.g-a {{ grid-template-columns: 1fr 1.32fr; }}
.g-b {{ grid-template-columns: 1fr 1fr; }}
.rx-rtbl td.rx-rtbl__td--note {{ white-space:normal; color:#414651; font-size:6.3pt; line-height:1.3; padding:2px 6px; }}
.sample {{ margin-top:8px; padding:5px 9px; border:1px solid #fedf89; background:#fffaeb; color:#b54708; border-radius:8px; font-weight:600; }}
.wf {{ display:grid; grid-template-columns: 1fr 1.6fr; gap:10px; align-items:start; }}
.mt-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:7px; }}
.rx-metric-tile--hero {{ grid-column:1 / -1; background:{tint}; border-color:{mix(tint, primary, 0.18)}; }}
.rx-metric-tile--hero .rx-metric-tile__value {{ font-size:18pt; color:{primary}; }}
.rx-metric-tile--hero .rx-metric-tile__comparison {{ color:#414651; white-space:normal; }}
.rx-metric-tile {{ display:flex; flex-direction:column; gap:1px; padding:8px 10px; border:1px solid #eaeaf0; border-radius:8px; background:#fff; min-width:0; }}
.rx-metric-tile__label {{ font-size:7pt; font-weight:500; color:#414651; }}
.rx-metric-tile__row {{ display:flex; align-items:baseline; gap:2px; }}
.rx-metric-tile__value {{ font-size:13.5pt; font-weight:600; line-height:1.25; color:#252b37; }}
.rx-metric-tile__comparison {{ font-size:6.6pt; font-weight:500; color:#717680; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.rxt__legend {{ display:flex; gap:14px; margin-bottom:2px; }}
.rxt__pill {{ display:inline-flex; align-items:center; gap:5px; font-size:6.4pt; font-weight:600; color:#414651; }}
.rxt__swatch {{ width:7px; height:7px; border-radius:2px; display:inline-block; }}
.chart {{ display:block; margin:2px 0 6px; }}
.chart .cv {{ font-size:8.4px; font-weight:600; fill:#252b37; }}
.chart .cx {{ font-size:8.4px; font-weight:700; fill:#717680; }}
.chart .cs {{ font-size:7.6px; font-weight:500; fill:#a4a7ae; }}
.rx-rtbl {{ border:2px solid rgba(112,115,147,.102); border-radius:10px; overflow:hidden; background:#fff; }}
.rx-rtbl__table {{ width:100%; table-layout:fixed; border-collapse:separate; border-spacing:0; font-size:7pt; line-height:1.3; color:#181d27; }}
.rx-rtbl th, .rx-rtbl td {{ height:16px; padding:0 6px; vertical-align:middle; text-align:left; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; background:#fff; border:0 solid #eaeaf0; }}
.rx-rtbl__th {{ padding:3px 6px !important; font-weight:700; color:#717680; border-right-width:1px !important; border-bottom-width:1px !important; }}
.rx-rtbl__th--num {{ text-align:right !important; }}
.rx-rtbl__rowlabel {{ font-weight:600; border-right-width:1px !important; border-bottom-width:1px !important; }}
.rx-rtbl__td {{ border-right-width:1px !important; border-bottom-width:1px !important; }}
.rx-rtbl__td--num {{ text-align:right !important; font-variant-numeric:tabular-nums; }}
.rx-rtbl tr > *:last-child {{ border-right-width:0 !important; }}
.rx-rtbl tbody tr:last-child > * {{ border-bottom-width:0 !important; }}
.rx-rtbl .rx-rtbl__group > * {{ background:#f5f5fa; border-bottom-width:1px; }}
.rx-rtbl__grouptitle {{ font-size:7.4pt; font-weight:700; padding:0 6px !important; }}
.rx-rtbl .rx-rtbl__tr--subject > * {{ background:{tint}; }}
.rx-rtbl .rx-rtbl__th--subject, .rx-rtbl .rx-rtbl__td--subject {{ background:{tint}; }}
.rx-rtbl .rx-rtbl__tr--total > * {{ background:#f5f5fa; font-weight:700; }}
.rx-rtbl__tr--total-first > * {{ border-top-width:1px !important; }}
.rx-rtbl__tr--strong > * {{ font-weight:700; }}
.rx-rtbl .rx-rtbl__tr--noi > * {{ border-top:1.5px solid {primary} !important; border-bottom:1.5px solid {primary} !important; }}
.rx-rtbl td.is-base {{ font-weight:800; color:{primary}; box-shadow: inset 0 0 0 1.5px {primary}; }}
.rx-detail-list {{ display:flex; flex-direction:column; gap:1px; margin-top:7px; }}
.rx-detail-list__row {{ display:flex; justify-content:space-between; gap:8px; line-height:1.5; }}
.rx-detail-list__label {{ font-size:6.8pt; font-weight:500; color:#414651; }}
.rx-chart-note {{ margin-top:4px; font-size:6.2pt; line-height:1.45; color:#717680; }}
.rx-alert {{ display:flex; flex-direction:column; gap:2px; padding:8px 10px; border:1px solid #fedf89; background:#fffaeb; border-radius:8px; color:#414651; }}
.rx-alert b {{ font-size:6.4pt; font-weight:700; color:#b54708; }}
.foot {{ display:flex; justify-content:space-between; gap:16px; margin-top:9px; font-size:5.8pt; color:#a4a7ae; }}
"""

    page_body = f"""
<header class="ph">
  <div class="ph__titlerow">
    <div>
      <div class="ph__identity"><h1 class="ph__title">{esc(deal.get('name'))}</h1>
</div>
      <div class="ph__facts">{esc(' · '.join(facts))}</div>
      {f'<div class="ph__mix">{mix_line}</div>' if mix_line else ''}
    </div>
    <div class="ph__aside">{brand_mark}<div class="ph__date">{esc(' · '.join(marks))}</div><div class="ph__date">Investment committee · {esc(date_label(memo.get('memo_date', date.today().isoformat())))}</div></div>
  </div>
  {summary_html}
  {f'<div class="sample">{esc(memo.get("sample_note") or "Layout preview: some figures are illustrative, not from the client model.")}</div>' if memo.get('sample') else ''}
</header>
<div class="grid g-a">
  <section class="card"><div class="card__head"><span class="card__title">Deal metrics</span></div>{metrics_html}</section>
  <section class="card"><div class="card__head"><span class="card__title">NOI over the hold</span></div>{hold_html}</section>
</div>
<div class="grid g-b">
  <section class="card"><div class="card__head"><span class="card__title">Capitalization</span></div>{cap_html}</section>
  <section class="card"><div class="card__head"><span class="card__title">{esc(sens.get('metric', 'IRR'))} sensitivity</span><span class="card__meta">{esc(sens.get('col_label', ''))} across · {esc(sens.get('row_label', ''))} down</span></div>{sens_html}</section>
</div>
{wf_html}
<div class="grid">
  <section class="card"><div class="card__head"><span class="card__title">Operating statement</span><span class="card__meta">Actuals from Radix · pro forma from the model</span></div>{ops_html}</section>
</div>
<div class="foot"><span>{esc(brand.get('disclaimer') or '')}</span><span>{esc(memo.get('account', ''))}</span></div>
"""
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(deal.get('name'))} IC memo</title><style>{css}</style></head><body>{page_body}</body></html>"



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
            for scale in ([1.0, 0.96, 0.92, 0.88, 0.84, 0.8, 0.76, 0.72] if one_page else [1.0]):
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
    """Editable version: the same content in a plain layout, plus the line-level T12 and unit mix as an appendix."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor, Inches

    colors = brand.get("colors", {})
    primary = colors.get("primary") if valid_hex(colors.get("primary")) else "#144a85"
    tint = colors.get("accent_tint") if valid_hex(colors.get("accent_tint")) else "#eff4fe"
    font = brand.get("fonts", {}).get("body", "Manrope")
    rgb = lambda h: RGBColor.from_string(h.lstrip("#").upper())
    deal, src = memo["deal"], memo.get("sources") or {}
    act, pf, terms, ret = memo.get("actuals") or {}, memo.get("proforma") or {}, memo.get("deal_terms") or {}, memo.get("returns") or {}
    cols = act.get("columns", [])

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(0.7)
    sec.top_margin = sec.bottom_margin = Inches(0.6)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = font, Pt(9)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), font)
    st.paragraph_format.space_after = Pt(3)

    def shade(cell, h):
        tcPr = cell._tc.get_or_add_tcPr()
        s = OxmlElement("w:shd")
        s.set(qn("w:val"), "clear"); s.set(qn("w:color"), "auto"); s.set(qn("w:fill"), h.lstrip("#"))
        tcPr.append(s)

    def heading(t):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        r = p.add_run(t.upper()); r.bold = True; r.font.size = Pt(8); r.font.color.rgb = rgb(primary)

    def small(t, color="#717680"):
        p = doc.add_paragraph(); r = p.add_run(t); r.font.size = Pt(7); r.font.color.rgb = rgb(color)

    def table(headers, rows, bold=(), shaded=()):
        t = doc.add_table(rows=1, cols=len(headers)); t.style = "Table Grid"
        for i, h in enumerate(headers):
            c = t.rows[0].cells[i]; c.text = ""
            r = c.paragraphs[0].add_run(h); r.bold = True; r.font.size = Pt(7.5)
            if i:
                c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
            shade(c, tint)
        for ri, row in enumerate(rows):
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = ""
                r = cells[i].paragraphs[0].add_run(str(v)); r.font.size = Pt(7.5); r.bold = ri in bold
                if i:
                    cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
                if ri in shaded:
                    shade(cells[i], tint)

    p = doc.add_paragraph(); r = p.add_run(deal.get("name", "")); r.bold = True; r.font.size = Pt(20)
    meta = [deal.get("address", ""), f"{fmt_int(deal.get('units'))} units"]
    if deal.get("year_built"):
        meta.append(f"{deal['year_built']} vintage")
    if terms.get("hold_years"):
        meta.append(f"{terms['hold_years']}-year hold")
    small(" · ".join(meta) + f" · {memo.get('status_label') or 'Screening memo'} · {date_label(memo.get('memo_date'))}")

    com = memo.get("commentary") or {}
    if com.get("text"):
        heading("Summary"); doc.add_paragraph(com["text"])

    if ret:
        heading("Returns")
        rows = []
        for name, key in (("Unlevered", "unlevered"), ("Levered", "levered"), ("LP", "lp")):
            r_ = ret.get(key)
            if r_:
                rows.append([name, fmt_ratio(r_.get("irr")), fmt_mult(r_.get("moic")),
                             fmt_ratio(r_.get("avg_coc")) if is_num(r_.get("avg_coc")) else "-", fmt_money(r_.get("profit"))])
        table(["", "IRR", "Multiple", "Avg CoC", "Profit"], rows, bold=(1,))
        ex = ret.get("exit") or {}
        small(f"Exit cap {fmt_ratio(ex.get('cap'), 2)} · gross sale proceeds {fmt_money(ex.get('gross_proceeds'))} · "
              f"going-in cap on pro forma {fmt_ratio(terms.get('going_in_cap_model'), 2)}")
    if is_num(der.get("required_equity")):
        p = doc.add_paragraph(); r = p.add_run(f"Required equity {fmt_money(der['required_equity'])}"); r.bold = True; r.font.size = Pt(11)
    if is_num(terms.get("price")):
        small(f"Purchase price {fmt_money(terms['price'])} ({fmt_money(der['price_per_unit'])} per unit). "
              f"Cap rate on T12 NOI {fmt_ratio(der['cap'].get('T12'), 2)} (derived).", NEUTRAL["ink"])

    cs, su = memo.get("capital_stack") or {}, memo.get("sources_uses") or {}
    if su.get("uses"):
        heading("Sources and uses")
        table(["Uses", "$", "%"], [[u["label"], fmt_money(u["amount"]), fmt_ratio(u["amount"] / der["uses_total"])] for u in su["uses"]]
              + [["Total", fmt_money(der["uses_total"]), "100%"]], bold=(len(su["uses"]),))
        table(["Sources", "$", "%"], [[s["label"], fmt_money(s["amount"]), fmt_ratio(s["amount"] / der["sources_total"])] for s in su["sources"]]
              + [["Total", fmt_money(der["sources_total"]), "100%"]], bold=(len(su["sources"]),))
        for t in cs.get("terms", []):
            small(t)

    wf = memo.get("waterfall") or {}
    if wf.get("partners") and memo.get("waterfall_option", "auto") != "never":
        heading("Equity waterfall")
        if wf.get("structure"):
            small(wf["structure"])
        if wf.get("tiers"):
            table(["Tier", "Hurdle", "LP", "GP"], [[t["label"], t.get("hurdle", ""), fmt_ratio(t.get("lp"), 0), fmt_ratio(t.get("gp"), 0)] for t in wf["tiers"]])
        table(["Partner", "Equity", "Distributions", "Profit", "IRR", "Multiple", "Promote"],
              [[x["label"], fmt_money(x.get("equity")), fmt_money(x.get("distributions")), fmt_money(x.get("profit")),
                fmt_ratio(x.get("irr")), fmt_mult(x.get("moic")), fmt_money(x.get("promote")) if is_num(x.get("promote")) and x.get("promote") else "-"] for x in wf["partners"]])
    if memo.get("sample"):
        small(memo.get("sample_note") or "Layout preview: some figures are illustrative, not from the client model.", "#b54708")

    sens = memo.get("sensitivity") or {}
    if sens.get("values"):
        heading(f"Sensitivity · {sens.get('metric', 'IRR')}")
        table([f"{sens.get('row_label', '')} / {sens.get('col_label', '')}"] + list(sens["cols"]),
              [[rl] + [fmt_ratio(v) for v in rv] for rl, rv in zip(sens["rows"], sens["values"])])
        small(sens.get("title", ""))

    heading("Operating statement · actual to pro forma")
    dnotes = {k: v for k, v in (pf.get("notes") or {}).items() if v}
    hdr = [""] + [c["label"] for c in cols] + ([pf.get("label", "Y1 pro forma"), "Change vs T12"] if pf else []) + (["Notes"] if dnotes else [])
    rows, bold, shaded = [], [], []

    def add(key, label, b=False, s=False):
        if key in ("egr", "opex", "noi"):
            vals, p_ = [(act.get(key) or {}).get(c["key"]) for c in cols], pf.get(key)
        else:
            vals, p_ = [der["groups"][key].get(c["key"]) for c in cols], (pf.get("groups") or {}).get(key)
        row = [label] + [fmt_money(v) for v in vals]
        if pf:
            a12 = vals[[c["key"] for c in cols].index("T12")] if "T12" in [c["key"] for c in cols] else None
            chg = p_ - a12 if is_num(p_) and is_num(a12) else None
            row += [fmt_money(p_), (("+" if chg > 0 else "-" if chg < 0 else "") + fmt_money(abs(chg))) if is_num(chg) else "-"]
        if dnotes:
            row.append(dnotes.get(key, ""))
        rows.append(row)
        if b:
            bold.append(len(rows) - 1)
        if s:
            shaded.append(len(rows) - 1)
    for k, l in REV_GROUPS:
        add(k, l)
    add("egr", "Effective gross revenue", True)
    for k, l in EXP_GROUPS:
        add(k, l)
    add("opex", "Total operating expenses", True)
    add("noi", "Net operating income", True, True)
    table(hdr, rows, bold=bold, shaded=shaded)

    hcf = memo.get("hold_cash_flow") or {}
    if hcf.get("noi"):
        heading("Hold-period cash flow")
        years = hcf.get("years") or [f"Y{i + 1}" for i in range(len(hcf["noi"]))]
        rows = []
        if hcf.get("egr"):
            rows.append(["Effective gross revenue"] + [fmt_money(v) for v in hcf["egr"]])
        if hcf.get("opex"):
            rows.append(["Operating expenses"] + [fmt_money(-abs(v)) for v in hcf["opex"]])
        rows.append(["NOI"] + [fmt_money(v) for v in hcf["noi"]])
        if any(hcf.get("debt_service") or []):
            rows.append(["Debt service"] + [fmt_money(-abs(v)) if v else "-" for v in hcf["debt_service"]])
        if hcf.get("net_cash_flow"):
            rows.append(["Net cash flow"] + [fmt_money(v) for v in hcf["net_cash_flow"]])
        if hcf.get("coc"):
            rows.append(["Cash-on-cash"] + [fmt_ratio(v) for v in hcf["coc"]])
        if any(hcf.get("dscr") or []):
            rows.append(["DSCR"] + [fmt_mult(v) for v in hcf["dscr"]])
        table([""] + years, rows)

    doc.add_page_break()
    heading("Appendix · operating statement by line (Radix)")
    rows, bold = [], []
    for sec_name, key in (("Revenue", "revenue"), ("Operating expenses", "expenses")):
        rows.append([sec_name] + [""] * len(cols)); bold.append(len(rows) - 1)
        for r_ in act.get(key, []):
            rows.append([r_["label"]] + [fmt_money(r_["values"].get(c["key"])) for c in cols])
    for key, label in (("egr", "Effective gross revenue"), ("opex", "Total operating expenses"), ("noi", "Net operating income")):
        rows.append([label] + [fmt_money((act.get(key) or {}).get(c["key"])) for c in cols]); bold.append(len(rows) - 1)
    table([""] + [c["label"] for c in cols], rows, bold=bold)
    small("Radix operating statement. " + "; ".join(f'{c["label"]} {c.get("window", "")}' for c in cols))
    um = memo.get("unit_mix") or {}
    if um.get("rows"):
        heading("Appendix · unit mix (Radix rent roll)")
        rws = [[unit_type(r), fmt_int(r.get("units")), fmt_int(r.get("avg_sf")), fmt_money(r.get("market_rent")),
                fmt_money(r.get("in_place_rent")), fmt_pct(r.get("occupied_pct"))] for r in um["rows"]]
        t = um.get("total") or {}
        rws.append(["Total / avg", fmt_int(t.get("units")), fmt_int(t.get("avg_sf")), fmt_money(t.get("market_rent")),
                    fmt_money(t.get("in_place_rent")), fmt_pct(t.get("occupied_pct"))])
        table(["Unit type", "Units", "Avg SF", "Market", "In-place", "Occ."], rws, bold=(len(rws) - 1,))
        small(f"Rent roll as of {date_label((src.get('rent_roll') or {}).get('as_of'))}")
    small(brand.get("disclaimer") or "")
    doc.save(str(docx_path))


# ---------- run summary ----------

def run_summary(memo, status, checks, placeholders, flags, outputs):
    lines = [f"# Run summary: {memo['deal'].get('name')} IC memo", "", f"Accuracy gate: **{status.replace('_', ' ')}**", "", "## Checks"]
    lines += [f"- {'PASS' if c['ok'] else 'FAIL'}: {c['check']}" + (f" ({c['detail']})" if c["detail"] and not c["ok"] else "") for c in checks]
    lines += ["", f"## Pre-send checks, not printed on the memo ({sum(f['fired'] for f in flags)} to look at, {sum(not f['fired'] for f in flags)} clear)"]
    lines += [f"- {'REVIEW' if f['fired'] else 'clear'}: {f['name']} ({f['test']}): {f['observed']}" for f in flags]
    lines += ["", "## Placeholders"] + ([f"- {p}" for p in placeholders] or ["- None"])
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
    if memo.get("schema") != "radix.ic_memo/v2":
        print(json.dumps({"status": "fail", "error": "memo.json must use schema radix.ic_memo/v2 (references/memo-schema.md)"}))
        sys.exit(1)
    der = derive(memo)
    shown = Shown()
    page = build_html(memo, brand, der, shown)
    status, checks, placeholders = run_gate(memo, der, shown)
    if status == "fail" and not a.force:
        print(json.dumps({"status": status, "failed": [c for c in checks if not c["ok"]]}, indent=2))
        sys.exit(2)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9]+", "-", memo["deal"].get("name", "deal")).strip("-") + "-IC-Memo"
    formats = {f.strip().lower() for f in a.formats.split(",")}
    outputs = []
    html_path = out / f"{stem}.html"
    html_path.write_text(page, encoding="utf-8")
    if "html" in formats:
        outputs.append(str(html_path))
    if "pdf" in formats:
        if write_pdf(html_path, out / f"{stem}.pdf", one_page=memo.get("variant", "one_pager") == "one_pager"):
            outputs.append(str(out / f"{stem}.pdf"))
        else:
            outputs.append(f"PDF not written: no PDF engine (playwright or weasyprint). HTML kept at {html_path}")
    if "docx" in formats:
        write_docx(memo, brand, der, out / f"{stem}.docx")
        outputs.append(str(out / f"{stem}.docx"))
    (out / f"{stem}-run-summary.md").write_text(run_summary(memo, status, checks, placeholders, der["flags"], outputs))
    print(json.dumps({"status": status, "outputs": outputs, "placeholders": placeholders,
                      "checks_to_look_at": [f"{f['name']}: {f['observed']}" for f in der["flags"] if f["fired"]],
                      "failed": [c for c in checks if not c["ok"]]}, indent=2))


if __name__ == "__main__":
    main()
