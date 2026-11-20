# Reading the client's model

Until Radix has a returns engine, price, returns, financing and sensitivity come from the client's own underwriting model. Models differ by firm, so read by label, not by position.

## What to pull

| Block | Look for labels like | Format in memo.json |
|---|---|---|
| Price | Purchase price, Bid price, Offer price, Acquisition price | number, `pricing.price` |
| Returns | Levered IRR, Unlevered IRR, Equity multiple / MOIC, Cash-on-cash (Year 1 or average), Hold period | ratios as decimals (`0.142`), `format: "pct"`; multiple `format: "multiple"`; hold `format: "years"` |
| Financing | Loan amount, LTV / LTC, Interest rate, Term, Interest-only period, Amortization, Required equity, JV split / LP-GP | money `format: "money"`, rates `format: "pct2"`, anything else `format: "text"` |
| Sensitivity | A grid of IRR (or equity multiple) by exit cap rate and rent growth, or by purchase price and exit cap | `sensitivity.rows`, `cols`, `values` (decimals), `format: "pct"` or `"multiple"` |

## How to read it

1. Open with `openpyxl` and `data_only=True` so you read calculated values, not formulas. If a value comes back `None` where a formula exists, the file was saved without calculated values: tell the user and ask them to open and re-save it in Excel.
2. Search every sheet for the labels above (case-insensitive). The value is usually in the next non-empty cell to the right or below.
3. Record each value's location in `sources.client_model.cells` (e.g. `"returns": "Returns!C14:C18"`). It goes in the run summary so the analyst can check it.
4. **More than one match** (scenarios, LP vs. GP IRR, several hold periods): list them and ask which to use. Don't choose.
5. **Percentages:** models store 14.2% as `0.142`. If a value is above 1 for an IRR or rate, it was typed as a whole number; divide by 100 and say so.
6. Put the file name in `sources.client_model.file`, and the model's as-of or version date in `as_of` if it shows one.

## When the agent can't read the file

If the model is a PDF or image, read the values off it the same way and record the page instead of a cell. If the model can't be read at all, leave the blocks `null` and list them as placeholders.
