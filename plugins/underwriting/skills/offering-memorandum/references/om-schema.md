# om.json (`radix.om/v1`)

The agent writes this file; `scripts/build_om.js` turns it into the deck. Leave a block empty or `null` when there's no source: the deck shows a flagged placeholder.

`deal`, `sources`, `snapshot`, `actuals` and `proforma` use the same shapes as the ic-memo skill's `radix.ic_memo/v2` (see `ic-memo/references/memo-schema.md`), including line `group` keys and `actuals.monthly`.

```json
{
  "schema": "radix.om/v1",
  "memo_date": "YYYY-MM-DD",
  "account": "Account name from the MCP result",
  "deal": {"name": "", "address": "", "units": 0, "year_built": 0, "building_type": "", "total_sf": 0, "market": ""},
  "sources": {"rent_roll": {"as_of": "YYYY-MM-DD"}, "operating_statement": {"label": "Actuals", "period_end": "YYYY-MM-DD"},
              "client_model": {"file": "model.xlsm", "cells": {}}},
  "offering": {"price": null, "price_label": "Unpriced", "offers_due": null,
               "terms": [{"label": "Financing", "value": "Offered free and clear of existing debt"}]},
  "summary": "Two sentences.",
  "highlights": [{"title": "Rents below market", "text": "One sentence with figures as the deck prints them."}],
  "snapshot": {"occupancy_pct": 0, "in_place_rent": 0, "market_rent": 0, "pct_of_market": 0, "vacant_units": 0},
  "floor_plans": {
    "rows": [{"plan": "W8311A", "beds": 1, "baths": 1, "units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "occupied_pct": 0}],
    "total": {"units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "occupied_pct": 0}
  },
  "bedrooms": {
    "rows": [{"label": "1 Bed", "units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "pct_of_market": 0,
              "last30_rent": 0, "last90_rent": 0, "occupied_pct": 0}],
    "total": {"label": "Total / avg", "units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "pct_of_market": 0, "last90_rent": 0, "occupied_pct": 0}
  },
  "actuals": {"columns": [], "revenue": [], "expenses": [], "egr": {}, "opex": {}, "noi": {}, "monthly": {"months": [], "egr": [], "opex": [], "noi": []}},
  "proforma": {"source": "client_model", "label": "Year 1 pro forma", "groups": {}, "egr": 0, "opex": 0, "noi": 0},
  "hold_cash_flow": {"years": ["Y1"], "egr": [0], "opex": [0], "noi": [0]},
  "assumptions": [{"label": "Market rent growth", "value": "0.0% per year"}],
  "comps": {
    "source": "How the comp set was chosen.",
    "subject": {"name": "", "city": "", "as_of": "YYYY-MM-DD"},
    "deals": [{"name": "", "city": "", "address": "", "as_of": "YYYY-MM-DD",
               "rows": [{"label": "1 Bed", "units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "occupied_pct": 0}],
               "total": {"units": 0, "avg_sf": 0, "market_rent": 0, "in_place_rent": 0, "occupied_pct": 0}}]
  },
  "sales_comps": null,
  "market_overview": null,
  "photos": [{"path": "hero.jpg", "caption": "Pool"}],
  "map": null,
  "contacts": [{"name": "", "title": "", "phone": "", "email": ""}]
}
```

## Rules

- Percents in `snapshot`, `floor_plans`, `bedrooms` and `comps` are percent numbers as the server returns them (`76.4`).
- `sales_comps`: `{"source": "", "rows": [{"name", "city", "sale_date", "units", "year_built", "price", "cap_rate"}]}` with `cap_rate` as a ratio. Only from a named source (broker research or web pages you opened); never estimated.
- `market_overview`: `{"text": "", "source": ""}`.
- `photos[].path` and `map.path` are local image files the user attached.

## Accuracy gate

The builder refuses to export (exit code 2) when:

- actual revenue lines don't sum to EGR, expense lines to OpEx, or NOI ≠ EGR - OpEx, in any column (±$1), or a line has no group
- pro forma groups don't sum to its EGR and OpEx, its NOI ≠ EGR - OpEx, or its NOI ≠ Year 1 NOI in the cash flow
- floor plans or bedrooms don't add to the deal's unit count, or snapshot occupancy ≠ the rent roll total
- the rent roll date, the actual column windows, or (when model data is used) the model file name is missing
- the summary or a highlight cites a figure the deck doesn't print (years, the street number and bare whole numbers under 100 are ignored)
