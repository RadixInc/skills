# Reading the client's model

The pro forma blocks (actuals to pro forma, pro forma cash flow, pro forma assumptions) come from the client's own underwriting model. Radix supplies the actuals; the model supplies the forward view. Models differ by firm, so read by label, not by position.

A broker OM doesn't print the buyer's returns, debt or equity. Don't read them.

## What to pull

| Field in the data file | Look for labels like |
|---|---|
| `proforma.categories` (Year 1, one figure per category) | The Year 1 column of the property cash flow: potential or market rent, loss to lease, vacancy, concessions, bad debt or collection loss, non-revenue units, other income, then each expense line |
| `proforma.egr`, `opex`, `noi` | Effective gross revenue (or income), total operating expenses, net operating income, Year 1 |
| `hold_cash_flow` | The same rows for every year of the hold: EGR, OpEx, NOI, and the revenue lines when shown |
| `assumptions` | Market rent growth, vacancy, loss to lease, concessions, other income growth, expense growth, real estate tax growth, hold period, exit cap rate, selling costs |

## How to read it

1. Open with `openpyxl` and `data_only=True` so you read calculated values, not formulas. If a value comes back `None` where a formula exists, the file was saved without calculated values: tell the user and ask them to open and re-save it in Excel.
2. Search every sheet for the labels above (case-insensitive). The value is usually in the next non-empty cell to the right or below.
3. Record each value's location in `sources.client_model.cells` (e.g. `"noi": "Cash Flow!E20"`) and the file name in `sources.client_model.file`.
4. **More than one match** (scenarios, several hold periods): list them and ask which to use. Don't choose.
5. **Signs:** make expenses positive; revenue deductions stay negative.
6. **Assumptions** are written as the model states them (`"3.0% per year"`, `"5.50%"`, `"5 years"`).

If the model is a PDF or image, read the values off it the same way and record the page instead of a cell. If it can't be read, leave the pro forma fields empty: those blocks are left out and listed.

## Mapping model lines to categories

| Category | Model lines |
|---|---|
| `gross_potential_rent` | Potential or market rent, renovation premium |
| `loss_to_lease` | Loss to lease, gain to lease |
| `vacancy` | Vacancy, renovation downtime |
| `concessions` | Concessions |
| `credit_loss` | Bad debt, collection loss, non-revenue units, model or employee units |
| `other_income` | Other income, reimbursements, RUBS, parking, storage, commercial income |
| `payroll` | Payroll, personnel |
| `repairs_maintenance` | Repairs and maintenance, turnover, make-ready |
| `contract_services` | Contract services, landscaping, security |
| `marketing` | Marketing, advertising, leasing commissions |
| `administrative` | General and administrative, other operating expenses |
| `utilities` | Utilities, electricity, water and sewer, gas, trash |
| `real_estate_taxes` | Real estate taxes, other taxes |
| `insurance` | Insurance |
| `management` | Management fee |

Reserves and capital expenditures are below NOI in most models; leave them out. If the model's NOI is after reserves, say so in the run summary.

## Radix underwriting model (.xlsm)

The Radix underwriting model export (`<deal number> - <deal name>-<account id>-<date>.xlsm`) has a fixed layout. Read the visible tabs and skip the hidden ones; opening it with `openpyxl` reads values only, and macros never run.

| Value | Where |
|---|---|
| Year 1 pro forma by line | `Property CF`, Year 1 column (D). Column C is the model's T1 annualized; don't use it as actuals, use Radix |
| Hold-period EGR, OpEx, NOI | `Property CF` rows "EFFECTIVE GROSS REVENUE", "TOTAL OPERATING EXPENSES" (negative), "NET OPERATING INCOME (AFT. RESERVES)", one column per year |
| Market rent growth | `Input` rows 78 to 82 |
| Vacancy and loss to lease by year | `Input` rows 114 and 116 |
| Hold period, exit cap | `Summary` "Hold Period"; exit cap in the reversion inputs |
