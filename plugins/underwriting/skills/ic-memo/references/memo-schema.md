# memo.json (`radix.ic_memo/v2`)

The agent writes this file; `scripts/render_memo.py` turns it into the memo. Leave any block you have no source for as `null`: the page shows a flagged placeholder.

The memo tells one story: **actuals** from Radix (T12, T3 and T1 annualized, rent roll), then the **pro forma** from the client's model, then what the plan returns.

```json
{
  "schema": "radix.ic_memo/v2",
  "variant": "one_pager",
  "status_label": "Screening memo",
  "strategy": null,
  "memo_date": "YYYY-MM-DD",
  "account": "Account name from the MCP result",
  "deal": {"name": "", "address": "", "units": 0, "year_built": 0, "building_type": "", "total_sf": 0, "market": ""},
  "sources": {
    "rent_roll": {"as_of": "YYYY-MM-DD"},
    "operating_statement": {"label": "Actuals", "period_end": "YYYY-MM-DD"},
    "client_model": {"file": "model.xlsm", "as_of": null, "cells": {"price": "Summary!G21"}}
  },
  "snapshot": {"occupancy_pct": 0, "in_place_rent": 0, "market_rent": 0, "pct_of_market": 0,
               "vacant_units": 0, "occupied_units": 0, "leases_expiring_next90": 0},
  "unit_mix": {"rows": [{"label": "1 Bed", "units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "occupied_pct": 0}],
               "total": {"units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "occupied_pct": 0}},
  "actuals": {
    "columns": [{"key": "T12", "label": "T12", "window": "Sep 2025 - Aug 2026"},
                {"key": "T3", "label": "T3 Ann.", "window": "Jun - Aug 2026"},
                {"key": "T1", "label": "T1 Ann.", "window": "Aug 2026"}],
    "revenue":  [{"label": "Gross potential rent", "group": "potential_rent", "values": {"T12": 0, "T3": 0, "T1": 0}}],
    "expenses": [{"label": "Personnel", "group": "controllable", "values": {"T12": 0, "T3": 0, "T1": 0}}],
    "egr": {"T12": 0}, "opex": {"T12": 0}, "noi": {"T12": 0},
    "monthly": {"months": ["2025-09"], "egr": [0], "opex": [0], "noi": [0]}
  },
  "proforma": {
    "source": "client_model", "label": "Y1 pro forma",
    "groups": {"potential_rent": 0, "loss_to_lease": 0, "vacancy_credit": 0, "other_income": 0,
               "controllable": 0, "utilities": 0, "taxes_insurance": 0, "management": 0},
    "egr": 0, "opex": 0, "noi": 0,
    "effective_rent": 0, "market_rent": 0, "physical_occupancy": 0.75,
    "notes": {"potential_rent": "Analyst's note", "other_income": null}
  },
  "deal_terms": {"price": 0, "price_source": "client_model", "all_in_cost": 0,
                 "going_in_cap_model": 0.0946, "hold_years": 7, "analysis_start": "YYYY-MM-DD"},
  "returns": {
    "unlevered": {"irr": 0.125, "moic": 1.96, "profit": 0},
    "levered":   {"irr": 0.125, "moic": 1.96, "profit": 0, "avg_coc": 0.082},
    "lp": null,
    "exit": {"cap": 0.05, "gross_proceeds": 0}
  },
  "capital_stack": {"layers": [{"label": "Senior debt", "amount": 0, "kind": "debt"},
                               {"label": "Equity", "amount": 0, "kind": "equity"}],
                    "terms": ["5.39% fixed, 60-month IO, 30-year amortization"]},
  "sources_uses": {"uses": [{"label": "Purchase price", "amount": 0}],
                   "sources": [{"label": "Equity", "amount": 0}]},
  "sensitivity": {"source": "client_model", "metric": "Levered IRR", "title": "",
                  "row_label": "Hold", "col_label": "Exit cap", "rows": ["7 yrs"], "cols": ["5.00%"],
                  "values": [[0.125]], "format": "pct", "base": {"row": "7 yrs", "col": "5.00%"}},
  "hold_cash_flow": {"years": ["Y1"], "egr": [0], "opex": [0], "noi": [0], "debt_service": [0], "capex": [0],
                     "net_cash_flow": [0], "coc": [0.087], "dscr": null},
  "commentary": {"status": "draft", "text": "Two or three sentences."}
}
```

## Rules

- **Groups.** Every actual line gets one `group`: `potential_rent`, `loss_to_lease`, `vacancy_credit` (vacancy, concessions, non-revenue units, collection loss), `other_income` (other residential income, reimbursements, parking, storage, commercial), `controllable` (repairs, contract services, turnover, landscaping, personnel, marketing, leasing commissions, administrative, security, other), `utilities`, `taxes_insurance` (real estate and other taxes, insurance), `management`. The pro forma uses the same groups, mapped from the model's own lines.
- **Signs.** Expenses are positive. Revenue deductions (vacancy, concessions, loss to lease) are negative, as the server returns them. Debt service and capex in `hold_cash_flow` are positive amounts.
- **Percents.** `snapshot` and `unit_mix` percents are percent numbers as the server returns them (`76.4`). Everything else is a ratio (`0.125` = 12.5%).
- **`actuals.monthly`** is the operating statement's `summaryByColumn` for the 12 months of the T12. It is kept for the trend view (not drawn on the one-pager).
- **`strategy`** (Value add, Core plus, Lease-up) only when the user or the model states it.
- **`commentary`** is the summary in the page head: 2 or 3 sentences, facts only, every figure as the page shows it.
- **`proforma.notes`** are the analyst's notes by group key (any of the eight groups, plus `egr`, `opex`, `noi`, `rent`, `occupancy`, `cap_rate`). They print in a Notes column on the operating statement, which only appears when a note exists. Never write them yourself. Pre-send checks are computed and never printed, see [pre-send-checks.md](pre-send-checks.md).

## Accuracy gate

The renderer refuses to export (exit code 2) when:

- actual revenue lines don't sum to EGR, expense lines to OpEx, or NOI ≠ EGR - OpEx, in any column (±$1)
- an actual line has no group
- pro forma groups don't sum to its EGR and OpEx, its NOI ≠ EGR - OpEx, or its NOI ≠ Year 1 NOI in the hold cash flow
- hold-period net cash flow ≠ NOI - debt service - capex in any year
- sources ≠ uses, or the capital stack ≠ total sources
- the unit mix doesn't add to the deal's units, or snapshot occupancy ≠ the rent roll total
- the rent roll date, the actual column windows, or (when any model block is used) the model file name is missing
- the summary or a line note cites a figure that isn't printed on the page (years and bare whole numbers under 100 are ignored)
