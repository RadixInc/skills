# blocks.json (`radix.deal_blocks/v1`)

The agent writes this file; `scripts/build_blocks.js` turns it into the blocks. Include only the data the picked blocks need; a picked block whose data is missing is skipped and reported.

`deal`, `sources` and `snapshot` use the same shapes as the ic-memo skill's `radix.ic_memo/v2`. The operating statement uses its own, finer **categories** (below), because OMs show more lines than the IC memo's groups.

```json
{
  "schema": "radix.deal_blocks/v1",
  "blocks": ["property_snapshot", "unit_mix", "rents_vs_market", "operating_history",
             "operating_statement", "proforma_cash_flow", "proforma_assumptions", "rent_comps"],
  "account": "Account name from the MCP result",
  "deal": {"name": "", "address": "", "units": 0, "year_built": 0, "building_type": "", "total_sf": 0, "market": ""},
  "sources": {"rent_roll": {"as_of": "YYYY-MM-DD"}, "operating_statement": {"label": "Actuals", "period_end": "YYYY-MM-DD"},
              "client_model": {"file": "model.xlsm", "cells": {}}},
  "snapshot": {"occupancy_pct": 0, "in_place_rent": 0, "market_rent": 0, "pct_of_market": 0, "vacant_units": 0},
  "unit_mix": {
    "rows": [{"beds": 1, "baths": 1, "units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "pct_of_market": 0,
              "last30_rent": 0, "last90_rent": 0, "occupied_pct": 0}],
    "total": {"units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "pct_of_market": 0, "last30_rent": 0, "last90_rent": 0, "occupied_pct": 0}
  },
  "actuals": {"columns": [{"key": "T12", "label": "T12", "window": "Sep 2025 - Aug 2026"}, {"key": "T3", "label": "T3 Ann.", "window": "Jun - Aug 2026"}],
              "revenue": [{"label": "Gross potential rent", "category": "gross_potential_rent", "values": {"T12": 0, "T3": 0}}],
              "expenses": [{"label": "Personnel", "category": "payroll", "values": {"T12": 0, "T3": 0}}],
              "egr": {}, "opex": {}, "noi": {}},
  "history": {"columns": [{"label": "2025 Ann.", "window": "Jul - Dec 2025, 6 months annualized", "egr": 0, "opex": 0, "noi": 0}]},
  "proforma": {"source": "client_model", "label": "Year 1 pro forma", "categories": {"gross_potential_rent": 0, "payroll": 0}, "egr": 0, "opex": 0, "noi": 0},
  "hold_cash_flow": {"years": ["Year 1"], "revenue": {"gross_potential_rent": [0], "loss_to_lease": [0]}, "egr": [0], "opex": [0], "noi": [0]},
  "assumptions": [{"label": "Market rent growth", "value": "0.0% per year"}],
  "comps": {
    "source": "How the comp set was chosen.",
    "deals": [{"name": "", "city": "", "as_of": "YYYY-MM-DD",
               "rows": [{"beds": 1, "baths": 1, "units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "occupied_pct": 0}],
               "total": {"units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "occupied_pct": 0}}]
  }
}
```

## Rules

- `blocks` lists block ids from [block-catalog.md](block-catalog.md); they render in catalog order. Empty or missing means every block.
- **Categories.** Every actual line gets one `category`, and the pro forma gives one figure per category:
  - Revenue: `gross_potential_rent`; `loss_to_lease`; `vacancy` (incl. renovation downtime); `concessions`; `credit_loss` (collection loss, bad debt, non-revenue units); `other_income` (other residential income, reimbursements, parking, storage, commercial).
  - Expenses: `payroll` (personnel); `repairs_maintenance` (repairs, turnover / make-ready); `contract_services` (contract services, landscaping, security); `marketing` (marketing, advertising, leasing commissions); `administrative` (administrative, other operating expenses); `utilities`; `real_estate_taxes` (real estate and other taxes); `insurance`; `management`.
- **Signs.** Expenses positive; revenue deductions negative, as the server returns them. `hold_cash_flow.opex` is positive.
- **`actuals.columns`**: T12 and T3 annualized. T1 isn't shown on any block.
- **`history.columns`**: one per calendar year from `get_operating_statement` with `period: "annual"` (EGR, OpEx and NOI from `summaryByColumn`), oldest first. A partial year is annualized by the server: label it "<year> Ann." (or "<year> YTD Ann." for the current year) and state the months in `window`. Leave `history` empty when every month is inside the T12.
- **`hold_cash_flow.revenue`**: optional, one array per revenue category, years in order, from the model.
- `unit_mix` and comp rows are always by bed / bath (`groupBy: "unitMixBath"`); the builder labels them from `beds` and `baths`.
- Percents in `snapshot`, `unit_mix` and `comps` are percent numbers as the server returns them (`76.4`).
- `assumptions` values are written as the model states them; the block prints them as given.
- There is no field for drafted text: blocks carry data and source lines only.

## Accuracy gate

The builder refuses to export (exit code 2) when, for the blocks being rendered:

- actual revenue lines don't sum to EGR, expense lines to OpEx, or NOI ≠ EGR - OpEx, in any column (±$1), a line has no known category, or a column window is missing
- a history column's NOI ≠ EGR - OpEx or its months aren't stated
- a pro forma category is missing, the categories don't sum to its EGR and OpEx, its NOI ≠ EGR - OpEx, or its NOI ≠ Year 1 NOI in the cash flow
- a cash-flow year's revenue lines don't sum to EGR, or its NOI ≠ EGR - OpEx
- a unit mix row has no beds or baths, the unit mix doesn't add to the deal's unit count, snapshot occupancy ≠ the rent roll total, or the rent roll date is missing
- a comp's rows don't add to its unit count
- a model-based block is used and the model file isn't named
