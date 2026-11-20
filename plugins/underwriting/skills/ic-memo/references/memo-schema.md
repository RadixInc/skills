# memo.json (`radix.ic_memo/v1`)

The agent writes this file; `scripts/render_memo.py` turns it into the memo. Leave any block you have no source for as `null`.

```json
{
  "schema": "radix.ic_memo/v1",
  "variant": "one_pager",
  "status_label": "Screening memo",
  "memo_date": "YYYY-MM-DD",
  "account": "Account name from the MCP result",
  "deal": {
    "name": "", "address": "", "units": 0, "year_built": 0,
    "building_type": "", "total_sf": 0, "market": "", "deal_status": ""
  },
  "sources": {
    "rent_roll": {"as_of": "YYYY-MM-DD"},
    "operating_statement": {"label": "Actuals", "period_end": "YYYY-MM-DD"},
    "client_model": {"file": "model.xlsx", "as_of": null, "cells": {"price": "Summary!B2"}}
  },
  "snapshot": {
    "occupancy_pct": 0, "in_place_rent": 0, "market_rent": 0, "pct_of_market": 0,
    "vacant_units": 0, "leases_expiring_next90": 0
  },
  "operations": {
    "columns": [{"key": "T12", "label": "T12", "window": "Sep 2025 - Aug 2026"}],
    "revenue":  [{"label": "Gross potential rent", "values": {"T12": 0}, "note": null}],
    "expenses": [{"label": "Personnel", "values": {"T12": 0}, "note": null}],
    "egr": {"T12": 0}, "opex": {"T12": 0}, "noi": {"T12": 0}
  },
  "unit_mix": {
    "rows": [{"label": "1 Bed", "units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "occupied_pct": 0}],
    "total": {"units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "occupied_pct": 0}
  },
  "pricing": {"price": null, "price_source": "client_model | radix | user", "price_label": "Purchase price"},
  "returns":   {"source": "client_model", "items": [{"label": "Levered IRR", "value": 0.142, "format": "pct"}]},
  "financing": {"source": "client_model", "items": [{"label": "Loan amount", "value": 0, "format": "money"}]},
  "sensitivity": {
    "source": "client_model", "title": "Levered IRR: exit cap rate vs. rent growth",
    "row_label": "Exit cap", "col_label": "Rent growth",
    "rows": ["5.50%"], "cols": ["2.0%"], "values": [[0.15]], "format": "pct"
  },
  "assumptions_vs_market": {"source": "", "rows": [{"label": "Rent growth Y1", "ours": "3.0%", "market": "2.4%"}]},
  "commentary": {"status": "draft", "text": "Paragraphs separated by \\n"},
  "risks": [{"risk": "", "mitigant": null}],
  "sample": false
}
```

## Rules

- Percent fields in `snapshot` and `unit_mix` are percent numbers as the server returns them (`76.4` = 76.4%). Percent values in `returns`, `financing` and `sensitivity` are ratios (`0.142` = 14.2%).
- Expense lines are positive; revenue deductions (vacancy, concessions, loss to lease) are negative, as the server returns them.
- `operations` column keys are free (`T12`, `T3`, `T1`, `Y1`). The auto run-rate notes need `T12` and `T3`.
- `note` on a line is the analyst's text. Leave it `null` and the renderer adds a grey derived flag when T3 annualized differs from T12 by 15% or more.
- `sample: true` prints a banner saying returns come from an illustrative model. Use it only for demos.

## Accuracy gate

The renderer refuses to export (exit code 2) when:

- revenue lines don't sum to EGR, or expense lines don't sum to OpEx, in any column (±$1)
- NOI ≠ EGR - OpEx in any column (±$1)
- unit mix rows don't sum to the total, or the total ≠ the deal's units
- snapshot occupancy ≠ the unit mix total occupancy
- the rent roll date or the operating statement windows are missing
- a returns, financing or sensitivity block has no source, or names the client model without a file
- commentary or risks cite a number that isn't in the data, in the format the memo shows it (years and bare whole numbers under 100, such as "T3" or "5-year", are ignored)
