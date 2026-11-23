# blocks.json (`radix.deal_blocks/v1`)

The agent writes this file; `scripts/build_blocks.js` turns it into the blocks. Include only the data the picked blocks need; a picked block whose data is missing is skipped and reported.

`deal`, `sources`, `snapshot`, `actuals` and `proforma` use the same shapes as the ic-memo skill's `radix.ic_memo/v2` (see `ic-memo/references/memo-schema.md`), including line `group` keys and `actuals.monthly`.

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
  "actuals": {"columns": [], "revenue": [], "expenses": [], "egr": {}, "opex": {}, "noi": {}, "monthly": {"months": [], "egr": [], "opex": [], "noi": []}},
  "proforma": {"source": "client_model", "label": "Year 1 pro forma", "groups": {}, "egr": 0, "opex": 0, "noi": 0},
  "hold_cash_flow": {"years": ["Y1"], "egr": [0], "opex": [0], "noi": [0]},
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
- `unit_mix` and comp rows are always by bed / bath (`groupBy: "unitMixBath"`); the builder labels them from `beds` and `baths`.
- Percents in `snapshot`, `unit_mix` and `comps` are percent numbers as the server returns them (`76.4`).
- `assumptions` values are written as the model states them; the block prints them as given.
- There is no field for drafted text: blocks carry data and source lines only.

## Accuracy gate

The builder refuses to export (exit code 2) when, for the blocks being rendered:

- actual revenue lines don't sum to EGR, expense lines to OpEx, or NOI ≠ EGR - OpEx, in any column (±$1), a line has no group, or a column window is missing
- pro forma groups don't sum to its EGR and OpEx, its NOI ≠ EGR - OpEx, or its NOI ≠ Year 1 NOI in the cash flow; or a cash-flow year's NOI ≠ EGR - OpEx
- a unit mix row has no beds or baths, the unit mix doesn't add to the deal's unit count, snapshot occupancy ≠ the rent roll total, or the rent roll date is missing
- a comp's rows don't add to its unit count
- a model-based block is used and the model file isn't named
