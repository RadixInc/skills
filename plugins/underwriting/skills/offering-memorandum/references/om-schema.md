# om.json (`radix.om/v2`)

The agent writes this file; `scripts/build_om.js` turns it into the OM deck.

An `om.json` is a `blocks.json` with the OM's own pages added:

- **Data for the blocks:** `deal`, `sources`, `snapshot`, `unit_mix`, `actuals`, `history`, `proforma`, `hold_cash_flow`, `assumptions` and `comps`, exactly as in [blocks-schema.md](blocks-schema.md), with the same accuracy checks. Leave `blocks` empty to use the OM recipe (every block except `property_snapshot`), or list block ids to leave some out.
- **The OM's own pages:** the fields below.

```json
{
  "schema": "radix.om/v2",
  "blocks": [],

  "offering": {
    "price": null,
    "price_label": "Unpriced",
    "offers_due": "YYYY-MM-DD",
    "terms": [{"label": "Financing", "value": "Offered free and clear of existing debt"}]
  },
  "summary": "Two sentences: what and where, occupancy on the rent roll date, T12 NOI.",
  "highlights": [{"title": "Rents below market", "text": "One sentence with figures as the deck prints them."}],

  "property_facts": [{"label": "Parking", "value": "312 spaces, 96 covered"}],
  "amenities": {"community": ["Pool", "Fitness center"], "unit": ["In-unit washer and dryer"]},
  "photos": [{"path": "cover.jpg", "caption": "Exterior"}],
  "map": {"path": "map.png"},

  "sales_comps": {
    "source": "Where the sales came from, with links",
    "rows": [{"name": "", "city": "", "sale_date": "YYYY-MM-DD", "units": 0, "year_built": 0, "price": 0, "price_per_unit": null, "cap_rate": null}]
  },
  "market_overview": {
    "points": [{"text": "One fact about the submarket, with its figure.", "source": "Publisher, title, date"}]
  }
}
```

## Rules

- `offering.price` is a number, or null with `price_label` ("Unpriced", "Call for offers"). Price per unit is derived when a price is given.
- `summary` and `highlights` (at most 4) are drafts for the broker to edit. Every figure in them must appear on a slide exactly as printed; the gate checks each one.
- `property_facts` are things the broker told you; Radix facts (address, units, year built, SF, occupancy) are drawn from `deal` and `snapshot` and don't go here.
- `photos[0]` is the cover; `photos[1..4]` fill the photos page. Paths are local files the user attached.
- `sales_comps.rows`: `cap_rate` is a percent number (`5.25`), and only when a source states it. `price_per_unit` is derived when left null.
- `market_overview.points`: at most 8; each needs a `source`.
- Anything left out becomes a flagged placeholder and is listed in the run summary.

## Accuracy gate

On top of the block checks in [blocks-schema.md](blocks-schema.md), the builder refuses to export (exit code 2) when:

- the summary or a highlight cites a figure no slide prints
- there are more than 4 highlights
- a sales comp has no sale date or price, or the sales comps have no source
- a market point has no source
