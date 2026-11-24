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

## Radix underwriting model (.xlsm)

The Radix underwriting model export (`<deal number> - <deal name>-<account id>-<date>.xlsm`) has a fixed layout. Read the visible output tabs and skip the hidden ones. Opening it with `openpyxl` reads values only; macros never run.

| Value | Where |
|---|---|
| Purchase price, price per unit | `Summary` row "Purchase Price", columns G and I |
| All-in cost | `Summary` row "All-in Cost", column G |
| Going-in cap (pro forma NOI), trailing cap (T1 annualized NOI) | `Summary` "Purchase Price" row: Forward cap rate (column O), Trailing cap rate (column M) |
| Unleveraged and leveraged IRR, equity multiple | `Summary` "Investment Summary": rows "Unleveraged" and "Leveraged", IRR and Eq. Mult. columns |
| Hold period | `Summary` "Hold Period" |
| Year 1 and average cash-on-cash | `Cash Flow` row "Cash on Cash Yield": first year column and TOTAL column |
| Year 1 EGR, OpEx, NOI | `Cash Flow` rows "Effective Gross Revenue", "Operating Expenses" (negative), "NET OPERATING INCOME", first year column |
| Equity, closing costs, loans | `Sources & Uses` "Sources & Uses at Closing" |
| Loan terms | `Summary` "Debt Summary" (all zeros means all cash) |
| Year 1 pro forma by line | `Property CF`, Year 1 column (D): Potential Market Rent, Renovation Premium, Loss to Lease, Vacancy, Renovation Downtime, Concessions, Non-Revenue Units, Collection Loss, Other Income (subtotal), EFFECTIVE GROSS REVENUE, each expense line (negative), TOTAL OPERATING EXPENSES, Net Operating Income. Column C is the model's T1 annualized; don't use it as actuals, use Radix |
| Pro forma effective rent, market rent, occupancy | `Property CF` rows "Effective Rent (average)", "Market Rent (average)", "Physical Occupancy" (Year 1 column) |
| Hold-period cash flow by year | `Cash Flow` rows 18 to 25 (EGR, OpEx, NOI, capex, operating cash flow), 42 (debt service), 62 (cash-on-cash), one column per year |
| Profit | `Cash Flow` TOTAL column of "UNLEVERAGED CASH FLOW" and "LEVERAGED CASH FLOW" |
| IRR by hold period and exit cap | `Sensitivity Analysis` "Unleveraged internal rate of return and equity multiple": hold periods down column K, exit caps across row 22, IRR and multiple on alternating rows |

When every loan is zero, say "all cash" in the financing block and note that leveraged and unleveraged returns are the same. Leveraged sensitivity grids are all zeros in that case; use the unleveraged grid.

Group mapping for `Property CF` lines: Potential Market Rent and Renovation Premium → `potential_rent`; Loss to Lease → `loss_to_lease`; Vacancy, Renovation Downtime, Concessions, Non-Revenue Units, Collection Loss → `vacancy_credit`; Other Income → `other_income`; Utilities → `utilities`; Insurance and Real Estate Taxes → `taxes_insurance`; Property Management Fee → `management`; every other expense line → `controllable`. Expenses are negative in the sheet; make them positive.

## Required equity and the waterfall

- **Required equity**: `Sources & Uses` "Equity" under sources at closing (in the Radix export, `Sources & Uses!C9`). This is the cash the buyer puts in, including closing costs; it is not the purchase price.
- **Waterfall**: the Radix export keeps a `Waterfall` tab that is hidden when no partnership is set up. If it's hidden and empty, the deal has no waterfall: leave `waterfall` as `null`. When it's set up, read the tiers (hurdle, LP and GP split) and, for each partner, equity, total distributions, profit, IRR, multiple and the GP's promote. Other models usually have a "Waterfall" or "Partnership" tab with the same items.

## Setup for the investment thesis

The thesis is read from how the model is set up, not only from its outputs. In the Radix underwriting model export, on `Input`:

- **Unit renovations** (rows 86 to 109): per floor plan, average renovation cost (`D`), rent bump after renovation (`E`), post-renovation market rent (`F`), units to be renovated by year (`G:J`); renovation downtime in days at `G107`.
- **Capital expenditures**: upfront funding at `G41`, projected capex at `F42`, property-wide capex from row 200.
- **Market rent growth**: rows 78 to 82.
- **Vacancy and loss to lease** by year: rows 114 and 116, with renovation downtime and structural vacancy in rows 121 to 124.

All zeros in the renovation block, zero capex and flat vacancy and rents mean the model has no business plan. See [investment-thesis.md](investment-thesis.md) for how these become the strategy and drivers.
