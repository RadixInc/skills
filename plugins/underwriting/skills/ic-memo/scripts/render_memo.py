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
              ("vacancy_credit", "Vacancy, concessions, credit loss"), ("other_income", "Other income")]
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


# ---------- risk flags (fixed rules, documented in references/risk-rules.md) ----------

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
                      [(f"Note {i + 1}", n) for i, n in enumerate(memo.get("analyst_notes") or [])]:
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
    return f'<div class="ph"><b>Needs {esc(source)}</b><span>{esc(label)}</span></div>'


def sparkline(actual, proforma, color_a, color_p, w=150, h=26):
    """Monthly actuals (annualized) in grey, then pro forma years in the accent, on one scale."""
    pts = [v for v in actual + proforma if is_num(v)]
    if len(pts) < 2 or not actual:
        return ""
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    gap = 8
    wa = (w - gap) * 0.55 if proforma else w
    wp = (w - gap) - wa if proforma else 0
    y = lambda v: h - 3 - (v - lo) / span * (h - 6)
    xa = [wa * i / max(len(actual) - 1, 1) for i in range(len(actual))]
    xp = [wa + gap + wp * i / max(len(proforma) - 1, 1) for i in range(len(proforma))]
    pa = " ".join(f"{x:.1f},{y(v):.1f}" for x, v in zip(xa, actual))
    out = f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" width="100%" height="{h}"><polyline points="{pa}" fill="none" stroke="{color_a}" stroke-width="1.3"/>'
    if proforma:
        pp = " ".join(f"{x:.1f},{y(v):.1f}" for x, v in zip(xp, proforma))
        out += (f'<line x1="{xa[-1]:.1f}" y1="{y(actual[-1]):.1f}" x2="{xp[0]:.1f}" y2="{y(proforma[0]):.1f}" stroke="{color_p}" stroke-width="1" stroke-dasharray="2 2"/>'
                f'<polyline points="{pp}" fill="none" stroke="{color_p}" stroke-width="1.5"/>'
                + "".join(f'<circle cx="{x:.1f}" cy="{y(v):.1f}" r="1.5" fill="{color_p}"/>' for x, v in zip(xp, proforma)))
    return out + "</svg>"


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
    model_name = (src.get("client_model") or {}).get("file") or ""
    cs = memo.get("capital_stack") or {}
    rr = src.get("rent_roll") or {}

    # ----- header
    logo = brand.get("logo") or {}
    brand_mark = (f'<img class="logo" src="{esc(logo["data_uri"])}" alt="">' if logo.get("data_uri")
                  else f'<span class="wordmark">{esc(logo.get("wordmark_text") or brand.get("firm", {}).get("display_name") or "")}</span>')
    meta = [deal.get("address", "").upper()]
    if units:
        meta.append(f"{S.add(fmt_int(units))} UNITS")
    if deal.get("year_built"):
        meta.append(f"{deal['year_built']} VINTAGE")
    if deal.get("total_sf"):
        meta.append(f"{S.add(fmt_int(deal['total_sf']))} SF")
    um = memo.get("unit_mix") or {}
    mix_parts = []
    for r in um.get("rows", []):
        if r.get("units"):
            mix_parts.append(f"{S.add(fmt_int(r['units']))} {r['label'].upper().replace(' BED', 'BR')}")
    meta2 = mix_parts + ([f"{S.add(fmt_pct(snap.get('occupancy_pct')))} OCCUPIED"] if is_num(snap.get("occupancy_pct")) else []) + \
        ([f"RENT ROLL {date_label(rr.get('as_of')).upper()}"] if rr.get("as_of") else [])
    chips = [c for c in (memo.get("strategy"), memo.get("status_label") or "Screening memo") if c]
    sub_right = []
    if terms.get("hold_years"):
        sub_right.append(f"{terms['hold_years']}-YR HOLD")
    if terms.get("analysis_start"):
        sub_right.append(f"START {date_label(terms['analysis_start'], True).upper()}")
    sub_right.append(date_label(memo.get("memo_date", date.today().isoformat())).upper())

    # ----- KPI row
    lev, unl = ret.get("levered") or {}, ret.get("unlevered") or {}
    equity = next((l["amount"] for l in cs.get("layers", []) if l.get("kind") == "equity"), None)

    def kpi(label, value, unit, sub):
        unit = unit if value != "-" else ""
        return (f'<div class="kpi"><div class="lab">{esc(label)}</div><div class="big">{esc(value)}<span class="u">{esc(unit)}</span></div>'
                f'<div class="sub">{esc(sub)}</div></div>')
    if ret:
        irr, mo, coc = lev.get("irr"), lev.get("moic"), lev.get("avg_coc")
        S.add(fmt_ratio(irr)); S.add(fmt_mult(mo)); S.add(fmt_ratio(coc))
        k1 = kpi("Levered IRR", f"{irr * 100:.1f}" if is_num(irr) else "-", "%", f"unlevered {S.add(fmt_ratio(unl.get('irr')))}")
        k2 = kpi("Equity multiple", f"{mo:.2f}" if is_num(mo) else "-", "x", f"on {S.add(fmt_compact(equity))} total equity" if is_num(equity) else "")
        k3 = kpi("Avg cash-on-cash", f"{coc * 100:.1f}" if is_num(coc) else "-", "%",
                 f"years 1 to {terms['hold_years']}" if terms.get("hold_years") else "hold average")
        S.money(equity)
    else:
        k1, k2, k3 = (kpi(l, "-", "", "needs client model") for l in ("Levered IRR", "Equity multiple", "Avg cash-on-cash"))
    dscr = [x for x in ((memo.get("hold_cash_flow") or {}).get("dscr") or []) if is_num(x)]
    if dscr:
        k4 = kpi("Min DSCR", f"{min(dscr):.2f}", "x", "lowest year of the hold")
        S.add(f"{min(dscr):.2f}x")
    else:
        cap = der["cap"].get("T12")
        S.add(fmt_ratio(cap, 2)); S.money(terms.get("price"))
        k4 = kpi("Going-in cap on T12", f"{cap * 100:.2f}" if is_num(cap) else "-", "%",
                 f"{S.add(fmt_compact(terms.get('price')))} · {S.money(der['price_per_unit'])} / unit" if is_num(terms.get("price")) else "needs price")

    # ----- returns
    if ret:
        def rrow(name, sub, r, strong=False):
            S.money(r.get("profit"))
            return (f'<tr{" class=strong" if strong else ""}><td>{esc(name)} <span class="q">{esc(sub)}</span></td>'
                    f'<td class="n">{S.add(fmt_ratio(r.get("irr")))}</td><td class="n">{S.add(fmt_mult(r.get("moic")))}</td>'
                    f'<td class="n">{S.add(fmt_ratio(r.get("avg_coc"))) if is_num(r.get("avg_coc")) else "-"}</td>'
                    f'<td class="n">{S.add(fmt_compact(r.get("profit")))}</td></tr>')
        rows = rrow("Unlevered", "property level", unl) + rrow("Levered", "deal level", lev, True)
        if ret.get("lp"):
            rows += rrow("LP", "net of fees and promote", ret["lp"])
        ex = ret.get("exit") or {}
        S.money(ex.get("gross_proceeds"))
        exit_pu = ex["gross_proceeds"] / units if is_num(ex.get("gross_proceeds")) and units else None
        strip = [("Exit cap" + (f" · Y{terms['hold_years']}" if terms.get("hold_years") else ""), S.add(fmt_ratio(ex.get("cap"), 2))),
                 ("Gross sale proceeds", S.add(fmt_compact(ex.get("gross_proceeds")))),
                 ("Exit $ / unit", S.money(exit_pu)),
                 ("Going-in cap, pro forma", S.add(fmt_ratio(terms.get("going_in_cap_model"), 2)))]
        strip_html = "".join(f'<div><div class="lab">{esc(a)}</div><div class="mid">{esc(b)}</div></div>' for a, b in strip)
        returns_html = (f'<table class="t"><thead><tr><th></th><th class="n">IRR</th><th class="n">Multiple</th><th class="n">Avg CoC</th>'
                        f'<th class="n">Profit</th></tr></thead><tbody>{rows}</tbody></table><div class="strip">{strip_html}</div>')
    else:
        returns_html = ph("Unlevered and levered IRR, multiple, cash-on-cash, profit, exit")

    # ----- capital stack
    if cs.get("layers"):
        tot = sum(l["amount"] for l in cs["layers"])
        shade = {"debt": primary, "equity": accent, "pref": mix(accent, "#ffffff", 0.45)}
        bar = "".join(f'<div style="flex:{l["amount"] / tot:.4f};background:{shade.get(l.get("kind"), accent)}"></div>' for l in cs["layers"] if l["amount"])
        legend = ""
        for l in cs["layers"]:
            S.money(l["amount"])
            legend += (f'<div class="lg"><span class="sw" style="background:{shade.get(l.get("kind"), accent)}"></span>{esc(l["label"])}'
                       f'<span class="r">{S.add(fmt_compact(l["amount"]))} · {S.add(fmt_ratio(l["amount"] / tot))}</span></div>')
        stack_html = f'<div class="bar">{bar}</div>{legend}<div class="terms">' + "".join(f"<div>{esc(t)}</div>" for t in cs.get("terms", [])) + "</div>"
    else:
        stack_html = ph("Debt and equity layers, loan terms")

    # ----- sources and uses
    su = memo.get("sources_uses") or {}
    if su.get("uses"):
        def su_rows(items, total):
            return "".join(f'<tr><td>{esc(i["label"])}</td><td class="n">{S.money(i["amount"])}</td><td class="n">{S.add(fmt_ratio(i["amount"] / total))}</td></tr>' for i in items) + \
                   f'<tr class="tot"><td>Total</td><td class="n">{S.money(total)}</td><td class="n">100%</td></tr>'
        su_html = (f'<table class="t"><thead><tr><th>Uses</th><th class="n">$</th><th class="n">%</th></tr></thead><tbody>{su_rows(su["uses"], der["uses_total"])}</tbody></table>'
                   f'<table class="t gap"><thead><tr><th>Sources</th><th class="n">$</th><th class="n">%</th></tr></thead><tbody>{su_rows(su["sources"], der["sources_total"])}</tbody></table>')
    else:
        su_html = ph("Sources and uses at closing")

    # ----- sensitivity heatmap
    sens = memo.get("sensitivity") or {}
    if sens.get("values"):
        flat = [v for r in sens["values"] for v in r if is_num(v)]
        lo, hi = min(flat), max(flat)
        base = sens.get("base") or {}
        body = ""
        for rl, rv in zip(sens["rows"], sens["values"]):
            cells = ""
            for cl, v in zip(sens["cols"], rv):
                bg = mix("#ffffff", primary, 0.08 + 0.82 * (v - lo) / ((hi - lo) or 1))
                fg = "#ffffff" if contrast(bg, "#ffffff") >= 4.5 else NEUTRAL["ink"]
                val = f"{v * 100:.1f}" if sens.get("format", "pct") == "pct" else f"{v:.2f}x"
                S.add(val + ("%" if sens.get("format", "pct") == "pct" else ""))
                is_base = base.get("row") == rl and base.get("col") == cl
                cells += f'<td class="hm{" base" if is_base else ""}" style="background:{bg};color:{fg}">{esc(val)}</td>'
            body += f'<tr><td class="rl">{esc(rl)}</td>{cells}</tr>'
        head = "".join(f'<th>{esc(c)}</th>' for c in sens["cols"])
        sens_html = (f'<table class="hm-t"><thead><tr><th class="corner">{esc(sens.get("row_label", ""))}</th>{head}</tr></thead><tbody>{body}</tbody></table>'
                     f'<div class="src">{esc(sens.get("title", ""))}. Outlined cell is the base case.</div>')
    else:
        sens_html = ph("IRR grid, for example exit cap rate by hold period")

    # ----- actual to pro forma tiles
    monthly, hcf = act.get("monthly") or {}, memo.get("hold_cash_flow") or {}
    tiles = []

    def tile(label, sub, a, p, d, spark="", worse_up=False, pts=False):
        if pts:
            dtxt = f"{d:+.1f} pts" if is_num(d) else ""
        else:
            dtxt = fmt_signed_pct(d) if is_num(d) else ""
            if is_num(d):
                S.add(f"{abs(d) * 100:.1f}%")
        S.add(dtxt)
        cls = ("dn" if (d > 0) == worse_up else "up") if is_num(d) and abs(d) >= 0.0005 else ""
        if p == "-":  # no pro forma: show the actual alone
            sub = sub.split(" to ")[0]
            return (f'<div class="tile"><div class="lab">{esc(label)}</div><div class="flow"><span class="p">{esc(a)}</span></div>'
                    f'<div class="d"></div>{spark}<div class="sub">{esc(sub)}</div></div>')
        return (f'<div class="tile"><div class="lab">{esc(label)}</div><div class="flow"><span class="a">{esc(a)}</span>'
                f'<span class="arr">→</span><span class="p">{esc(p)}</span></div><div class="d {cls}">{esc(dtxt)}</div>'
                f'{spark}<div class="sub">{esc(sub)}</div></div>')
    if is_num(snap.get("in_place_rent")):
        r_pf = pf.get("effective_rent")
        d_r = (r_pf - snap["in_place_rent"]) / snap["in_place_rent"] if is_num(r_pf) else None
        tiles.append(tile("Rent / unit / mo", "in-place to pro forma effective", S.money(snap["in_place_rent"]), S.money(r_pf) if is_num(r_pf) else "-", d_r))
    if is_num(snap.get("occupancy_pct")):
        o_pf = pf.get("physical_occupancy")
        d_o = o_pf * 100 - snap["occupancy_pct"] if is_num(o_pf) else None
        tiles.append(tile("Occupancy", "rent roll to pro forma", S.add(fmt_pct(snap["occupancy_pct"])), S.add(fmt_ratio(o_pf)) if is_num(o_pf) else "-", d_o, pts=True))
    for key, label, worse_up in (("egr", "EGR", False), ("opex", "OpEx", True), ("noi", "NOI", False)):
        a, p = (act.get(key) or {}).get("T12"), pf.get(key)
        S.money(a); S.money(p)
        spark = sparkline([x * 12 for x in monthly.get(key, []) if is_num(x)], hcf.get(key) or ([] if key != "noi" else []), NEUTRAL["hush"], accent)
        tiles.append(tile(f"{label} (annual)", "T12 actual to Y1 pro forma", S.add(fmt_compact(a)), S.add(fmt_compact(p)) if is_num(p) else "-",
                          der["pf_delta"].get(key), spark, worse_up))
    tiles_html = "".join(tiles)

    # ----- operating statement: grouped actuals, then pro forma
    cols = act.get("columns", [])
    has_pf = bool(pf)
    head = "".join(f'<th class="n">{esc(c["label"])}</th>' for c in cols)
    head += (f'<th class="n pf">{esc(pf.get("label", "Y1 pro forma"))}</th><th class="n">Change vs T12</th>' if has_pf else "")

    def grow(key, label, cls=""):
        if key in ("egr", "opex", "noi"):
            vals, p = [(act.get(key) or {}).get(c["key"]) for c in cols], pf.get(key)
        else:
            vals, p = [der["groups"][key].get(c["key"]) for c in cols], (pf.get("groups") or {}).get(key)
        tds = "".join(f'<td class="n">{S.money(v)}</td>' for v in vals)
        if has_pf:
            a12 = vals[[c["key"] for c in cols].index("T12")] if "T12" in [c["key"] for c in cols] else None
            chg = p - a12 if is_num(p) and is_num(a12) else None
            ctxt = ("+" if chg > 0 else "-" if chg < 0 else "") + fmt_compact(abs(chg)) if is_num(chg) and abs(chg) >= 1 else ("$0" if is_num(chg) else "-")
            S.money(chg)
            tds += f'<td class="n pf">{S.money(p)}</td><td class="n dl">{S.add(ctxt)}</td>'
        return f'<tr class="{cls}"><td>{esc(label)}</td>{tds}</tr>'
    span = len(cols) + 1 + (2 if has_pf else 0)
    ops_rows = (f'<tr class="sec"><td colspan="{span}">Revenue</td></tr>' + "".join(grow(k, l) for k, l in REV_GROUPS) +
                grow("egr", "Effective gross revenue", "tot") +
                f'<tr class="sec"><td colspan="{span}">Operating expenses</td></tr>' + "".join(grow(k, l) for k, l in EXP_GROUPS) +
                grow("opex", "Total operating expenses", "tot") + grow("noi", "Net operating income", "noi"))
    if is_num(terms.get("price")):
        caps = "".join(f'<td class="n">{S.add(fmt_ratio(der["cap"].get(c["key"]), 2))}</td>' for c in cols)
        if has_pf:
            pf_cap = pf["noi"] / terms["price"] if is_num(pf.get("noi")) else None
            caps += f'<td class="n pf">{S.add(fmt_ratio(pf_cap, 2))}</td><td></td>'
        ops_rows += f'<tr class="sub"><td>Cap rate on purchase price</td>{caps}</tr>'
    windows = "; ".join(f'{c["label"]} {c["window"]}' for c in cols if c.get("window"))
    ops_html = (f'<table class="t ops"><thead><tr><th></th>{head}</tr></thead><tbody>{ops_rows}</tbody></table>'
                f'<div class="src">Actuals from the Radix operating statement ({esc(windows)}). '
                + (f'Pro forma from {esc(model_name)}. ' if has_pf else "") + 'Groups, cap rates and changes derived.</div>')

    # ----- risk flags
    flags = der["flags"]
    fired = [f for f in flags if f["fired"]]
    for f in fired:
        for tok in NUM_TOKEN.findall(f["observed"]):
            S.add(tok)
    flags_html = "".join(f'<div class="flag"><div class="fn">{esc(f["name"])}</div><div class="fo">{esc(f["observed"])}</div>'
                         f'<div class="ft">rule: {esc(f["test"])}</div></div>' for f in fired) or '<div class="sub">No rules fired.</div>'
    flags_html += "".join(f'<div class="note">{esc(n)}</div>' for n in memo.get("analyst_notes") or [])

    # ----- hold-period cash flow
    if hcf.get("noi"):
        years = hcf.get("years") or [f"Y{i + 1}" for i in range(len(hcf["noi"]))]

        def hrow(label, vals, kind="money", cls=""):
            if not vals:
                return ""
            def f(v):
                if not is_num(v):
                    return "-"
                if kind == "money":
                    S.money(v)
                    return S.add(fmt_compact(v))
                if kind == "neg":
                    S.money(v)
                    return f"({S.add(fmt_compact(abs(v)))})" if v else "-"
                if kind == "pct":
                    return S.add(fmt_ratio(v))
                return S.add(fmt_mult(v))
            return f'<tr class="{cls}"><td>{esc(label)}</td>' + "".join(f'<td class="n">{esc(f(v))}</td>' for v in vals) + "</tr>"
        has_debt = any(is_num(v) and v for v in hcf.get("debt_service") or [])
        has_capex = any(is_num(v) and v for v in hcf.get("capex") or [])
        hcf_html = (f'<table class="t hcf"><thead><tr><th></th>' + "".join(f'<th class="n">{esc(y)}</th>' for y in years) + '</tr></thead><tbody>' +
                    hrow("Effective gross revenue", hcf.get("egr")) + hrow("Operating expenses", hcf.get("opex"), "neg") +
                    hrow("NOI", hcf["noi"], "money", "strongrow") +
                    (hrow("Debt service", hcf.get("debt_service"), "neg") if has_debt else "") +
                    (hrow("Capital expenditures", hcf.get("capex"), "neg") if has_capex else "") +
                    hrow("Net cash flow", hcf.get("net_cash_flow"), "money", "tot") +
                    hrow("Cash-on-cash", hcf.get("coc"), "pct") + (hrow("DSCR", hcf.get("dscr"), "x") if has_debt else "") +
                    "</tbody></table>")
        if not has_debt:
            hcf_html += '<div class="src">No debt in the model: net cash flow equals NOI.</div>'
    else:
        hcf_html = ph("NOI, debt service, net cash flow and cash-on-cash by year")

    # ----- footer
    com = memo.get("commentary") or {}
    left_src = [f"Radix · {memo.get('account', '')}", f"Rent roll {date_label(rr.get('as_of'))}",
                f"T12 through {date_label((src.get('operating_statement') or {}).get('period_end'), True)}"] + ([model_name] if model_name else [])
    all_cash = cs.get("layers") and not any(l.get("kind") == "debt" for l in cs["layers"])

    css = f"""
{font_face_css()}
@page {{ size: Letter; margin: 0.42in 0.45in 0.4in 0.45in; }}
* {{ box-sizing: border-box; }}
html, body {{ margin:0; padding:0; background:#fff; }}
body {{ font-family:'{font}', Arial, sans-serif; color:{NEUTRAL['ink']}; font-size:7.3pt; line-height:1.35; letter-spacing:-0.004em;
       -webkit-print-color-adjust:exact; print-color-adjust:exact; font-variant-numeric:tabular-nums; }}
.lab, th {{ font-size:5.8pt; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:{NEUTRAL['faint']}; }}
.hd {{ display:flex; justify-content:space-between; align-items:flex-start; padding-bottom:10px; border-bottom:2px solid {NEUTRAL['ink']}; }}
.hd h1 {{ margin:0; font-size:21pt; font-weight:600; letter-spacing:-0.025em; line-height:1.05; color:{NEUTRAL['ink']}; }}
.meta {{ margin-top:6px; font-size:5.9pt; letter-spacing:.09em; color:{NEUTRAL['faint']}; font-weight:600; }}
.meta + .meta {{ margin-top:2px; }}
.hr {{ text-align:right; }}
.chips {{ display:flex; gap:6px; justify-content:flex-end; align-items:center; }}
.chip {{ border:1px solid {NEUTRAL['rule_strong']}; border-radius:999px; padding:2px 8px; font-size:5.8pt; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:{NEUTRAL['muted']}; }}
.wordmark {{ font-weight:800; font-size:11.5pt; letter-spacing:-0.02em; color:{primary}; margin-left:6px; }}
.logo {{ max-height:18px; max-width:120px; margin-left:6px; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); border-bottom:1px solid {NEUTRAL['rule']}; }}
.kpi {{ padding:11px 12px 11px 0; }}
.kpi + .kpi {{ border-left:1px solid {NEUTRAL['rule']}; padding-left:12px; }}
.big {{ font-size:23pt; font-weight:500; letter-spacing:-0.03em; line-height:1.1; margin-top:5px; color:{NEUTRAL['strong']}; }}
.big .u {{ font-size:11pt; color:{NEUTRAL['faint']}; margin-left:1px; }}
.sub {{ font-size:6.2pt; color:{NEUTRAL['faint']}; margin-top:3px; }}
.row {{ display:grid; gap:10px; margin-top:10px; }}
.c2 {{ grid-template-columns:1.6fr 1fr; }}
.c2b {{ grid-template-columns:1fr 1.45fr; }}
.card {{ border:1px solid {NEUTRAL['rule']}; border-radius:8px; padding:10px 12px; background:#fff; break-inside:avoid; }}
.card.soft {{ background:{NEUTRAL['panel']}; }}
.ch {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:6px; }}
.ch .lab {{ color:{NEUTRAL['ink']}; }}
.ch .lab.r {{ color:{NEUTRAL['hush']}; }}
table.t {{ width:100%; border-collapse:collapse; }}
table.t th {{ text-align:left; padding:0 0 4px; border-bottom:1px solid {NEUTRAL['rule_strong']}; }}
table.t td {{ padding:2.6px 0; border-bottom:1px solid {NEUTRAL['rule']}; }}
table.t.gap {{ margin-top:8px; }}
.n {{ text-align:right; white-space:nowrap; }}
table.t td.n, table.t th.n {{ padding-left:8px; text-align:right; }}
.q {{ color:{NEUTRAL['faint']}; font-size:6.2pt; }}
tr.strong td {{ font-weight:700; color:{NEUTRAL['strong']}; }}
tr.strongrow td {{ font-weight:700; }}
tr.tot td {{ font-weight:700; border-top:1px solid {NEUTRAL['ink']}; border-bottom:0; }}
tr.sec td {{ font-size:5.8pt; font-weight:700; letter-spacing:.09em; text-transform:uppercase; color:{NEUTRAL['faint']}; padding-top:6px; border-bottom:0; }}
tr.noi td {{ font-weight:800; background:{tint}; border-bottom:0; }}
tr.noi td:first-child {{ padding-left:4px; }}
tr.sub td {{ color:{NEUTRAL['faint']}; border-bottom:0; }}
td.pf, th.pf {{ background:{mix('#ffffff', accent, 0.07)}; padding-right:5px; }}
tr.noi td.pf {{ background:{mix(tint, accent, 0.12)}; }}
td.dl {{ color:{NEUTRAL['muted']}; }}
.strip {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-top:8px; padding-top:8px; border-top:1px dashed {NEUTRAL['rule_strong']}; }}
.mid {{ font-size:10.5pt; font-weight:600; letter-spacing:-0.02em; margin-top:2px; color:{NEUTRAL['strong']}; }}
.bar {{ display:flex; height:22px; border-radius:4px; overflow:hidden; gap:2px; margin:4px 0 8px; }}
.lg {{ display:flex; align-items:center; gap:6px; padding:2px 0; }}
.lg .sw {{ width:7px; height:7px; border-radius:2px; display:inline-block; }}
.lg .r {{ margin-left:auto; color:{NEUTRAL['muted']}; }}
.terms {{ margin-top:8px; padding-top:7px; border-top:1px dashed {NEUTRAL['rule_strong']}; font-size:6.2pt; color:{NEUTRAL['faint']}; line-height:1.55; }}
.hm-t {{ width:100%; border-collapse:separate; border-spacing:2px; }}
.hm-t th {{ padding:2px 4px; text-align:right; }}
.hm-t th.corner {{ text-align:left; }}
.hm-t td.rl {{ font-weight:700; color:{NEUTRAL['muted']}; padding-right:6px; white-space:nowrap; }}
.hm-t td.hm {{ padding:5px 7px; border-radius:3px; font-weight:600; text-align:right; }}
.hm-t td.base {{ outline:2px solid {NEUTRAL['ink']}; outline-offset:-2px; }}
.tiles {{ display:grid; grid-template-columns:repeat(5,1fr); border-top:1px solid {NEUTRAL['rule']}; border-bottom:1px solid {NEUTRAL['rule']}; margin-top:10px; }}
.tile {{ padding:9px 10px 8px 0; }}
.tile + .tile {{ border-left:1px solid {NEUTRAL['rule']}; padding-left:10px; }}
.flow {{ display:flex; align-items:baseline; gap:4px; margin-top:5px; white-space:nowrap; }}
.flow .a {{ font-size:9.2pt; color:{NEUTRAL['faint']}; font-weight:500; }}
.flow .arr {{ color:{NEUTRAL['hush']}; }}
.flow .p {{ font-size:9.2pt; font-weight:700; color:{NEUTRAL['strong']}; }}
.d {{ font-size:6.2pt; font-weight:700; color:{NEUTRAL['muted']}; margin-top:1px; }}
.spark {{ display:block; margin:3px 0 0; }}
.flag {{ padding:4px 0; border-bottom:1px solid {NEUTRAL['rule']}; }}
.flag:last-child {{ border-bottom:0; }}
.fn {{ font-weight:700; color:{NEUTRAL['strong']}; }}
.fo {{ color:{NEUTRAL['warn']}; font-weight:600; }}
.ft {{ font-size:5.8pt; color:{NEUTRAL['hush']}; }}
.note {{ padding:4px 0; border-top:1px dashed {NEUTRAL['rule_strong']}; }}
.src {{ margin-top:5px; font-size:5.8pt; color:{NEUTRAL['hush']}; }}
.ph {{ border:1px dashed {NEUTRAL['warn']}; background:{NEUTRAL['warn_bg']}; border-radius:6px; padding:7px 9px; display:flex; flex-direction:column; gap:2px; color:{NEUTRAL['muted']}; }}
.ph b {{ font-size:5.8pt; letter-spacing:.08em; text-transform:uppercase; color:{NEUTRAL['warn']}; }}
.ft-row {{ display:grid; grid-template-columns:1fr 2.3fr 1fr; gap:14px; align-items:center; margin-top:12px; padding-top:9px; border-top:1px solid {NEUTRAL['rule_strong']}; }}
.ft-src {{ font-size:5.6pt; letter-spacing:.07em; text-transform:uppercase; color:{NEUTRAL['hush']}; line-height:1.6; }}
.summary {{ text-align:center; font-size:7.6pt; font-style:italic; color:{NEUTRAL['muted']}; line-height:1.45; }}
.summary .draft {{ display:block; font-style:normal; font-size:5.6pt; letter-spacing:.08em; text-transform:uppercase; color:{NEUTRAL['warn']}; margin-top:3px; font-weight:700; }}
.ft-brand {{ text-align:right; font-size:6.4pt; color:{NEUTRAL['faint']}; }}
.ft-brand b {{ color:{primary}; font-weight:800; }}
.disc {{ margin-top:6px; font-size:5.4pt; color:{NEUTRAL['hush']}; }}
"""

    body = f"""
<div class="hd">
  <div><h1>{esc(deal.get('name'))}</h1><div class="meta">{esc(' · '.join(meta))}</div>
  {f'<div class="meta">{esc(" · ".join(meta2))}</div>' if meta2 else ''}</div>
  <div class="hr"><div class="chips">{''.join(f'<span class="chip">{esc(c)}</span>' for c in chips)}{brand_mark}</div>
  <div class="meta">{esc(' · '.join(sub_right))}</div></div>
</div>
<div class="kpis">{k1}{k2}{k3}{k4}</div>
<div class="row c2">
  <div class="card"><div class="ch"><span class="lab">Returns</span><span class="lab r">{'All cash' if all_cash else 'Deal level'}</span></div>{returns_html}</div>
  <div class="card soft"><div class="ch"><span class="lab">Capital stack</span></div>{stack_html}</div>
</div>
<div class="row c2b">
  <div class="card"><div class="ch"><span class="lab">Sources and uses</span><span class="lab r">at closing</span></div>{su_html}</div>
  <div class="card"><div class="ch"><span class="lab">Sensitivity · {esc(sens.get('metric', 'IRR'))}</span><span class="lab r">{esc(sens.get('col_label', ''))} × {esc(sens.get('row_label', ''))}</span></div>{sens_html}</div>
</div>
<div class="tiles">{tiles_html}</div>
<div class="row c2">
  <div class="card"><div class="ch"><span class="lab">Operating statement · actual to pro forma</span><span class="lab r">$ annual</span></div>{ops_html}</div>
  <div class="card"><div class="ch"><span class="lab">Risk flags · {len(fired)} of {len(flags)} rules fired</span></div>{flags_html}</div>
</div>
<div class="row"><div class="card"><div class="ch"><span class="lab">Hold-period cash flow</span><span class="lab r">pre-promote · $</span></div>{hcf_html}</div></div>
<div class="ft-row">
  <div class="ft-src">{'<br>'.join(esc(s) for s in left_src)}</div>
  <div class="summary">{esc(com.get('text') or '')}{'<span class="draft">Draft for analyst review</span>' if com.get('text') and com.get('status', 'draft') == 'draft' else ''}</div>
  <div class="ft-brand">Prepared with <b>Radix</b></div>
</div>
<div class="disc">{esc(brand.get('disclaimer') or '')}</div>
"""
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(deal.get('name'))} IC memo</title><style>{css}</style></head><body>{body}</body></html>"


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
        heading("Summary"); doc.add_paragraph(com["text"]); small("Draft for analyst review", "#b54708")

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

    sens = memo.get("sensitivity") or {}
    if sens.get("values"):
        heading(f"Sensitivity · {sens.get('metric', 'IRR')}")
        table([f"{sens.get('row_label', '')} / {sens.get('col_label', '')}"] + list(sens["cols"]),
              [[rl] + [fmt_ratio(v) for v in rv] for rl, rv in zip(sens["rows"], sens["values"])])
        small(sens.get("title", ""))

    heading("Operating statement · actual to pro forma")
    hdr = [""] + [c["label"] for c in cols] + ([pf.get("label", "Y1 pro forma"), "Change vs T12"] if pf else [])
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

    heading(f"Risk flags · {sum(f['fired'] for f in der['flags'])} of {len(der['flags'])} rules fired")
    for f in der["flags"]:
        if f["fired"]:
            p = doc.add_paragraph(style="List Bullet"); r = p.add_run(f["name"] + ": "); r.bold = True
            p.add_run(f["observed"])
            small(f"rule: {f['test']}", "#a4a7ae")
    for n in memo.get("analyst_notes") or []:
        doc.add_paragraph(n, style="List Bullet")

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
        rws = [[r["label"], fmt_int(r.get("units")), fmt_int(r.get("avg_sf")), fmt_money(r.get("market_rent")),
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
    lines += ["", f"## Risk flags ({sum(f['fired'] for f in flags)} of {len(flags)} fired)"]
    lines += [f"- {'FIRED' if f['fired'] else 'clear'}: {f['name']} ({f['test']}): {f['observed']}" for f in flags]
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
                      "flags_fired": [f["name"] for f in der["flags"] if f["fired"]],
                      "failed": [c for c in checks if not c["ok"]]}, indent=2))


if __name__ == "__main__":
    main()
