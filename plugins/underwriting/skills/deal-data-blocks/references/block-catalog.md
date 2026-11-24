# Block catalog

Every block has the same frame: the block title, a subject line (deal name and the data's date or period), the content, and a source line. The content below is fixed for each block; only the brand's three colors change.

| Block id | Title on the block | What it shows | Source | Needs |
|---|---|---|---|---|
| `property_snapshot` | Property snapshot | 8 tiles: units, year built, rentable SF, average unit size, occupancy, average market rent, average in-place rent, in-place as % of market | Radix deal record and rent roll | `get_deal_details`, `get_deal_summary`, `get_floor_plan_summary` (unitMixBath) |
| `unit_mix` | Unit mix | Table by bed / bath: units, % of units, avg SF, market rent and rent per SF, in-place rent and rent per SF, occupied; total row; units by unit type bar chart | Radix rent roll | `get_floor_plan_summary` (unitMixBath) |
| `rents_vs_market` | Rents vs. market | Market, in-place and last-90-days lease rent by bed / bath (chart and table), gap to market per unit, in-place as % of market | Radix rent roll | `get_floor_plan_summary` (unitMixBath) |
| `operating_history` | Operating history | Each period Radix holds side by side: calendar years (partial years annualized and labeled), T12 and T3 annualized; EGR, OpEx and NOI with per-unit figures and expense ratio; one clustered bar chart. Only when Radix holds more than 12 months | Radix operating statements | `get_operating_statement` (annual) and the T12 call |
| `operating_statement` | Operating statement, or Actuals to pro forma with the model | T12 with per unit and T3 annualized, in the OM line breakdown (gross potential rent, loss to lease, vacancy, concessions, bad debt and non-revenue units, other income; payroll, repairs and turnover, contract services, marketing, G&A, utilities, real estate taxes, insurance, management); with the client's model, the Year 1 pro forma, per unit and change vs. T12 | Radix operating statement, client's model | `get_operating_statement`; the model |
| `proforma_cash_flow` | Pro forma cash flow | Revenue lines, EGR, OpEx and NOI by year over the hold, NOI per unit and NOI growth | Client's model | The model |
| `proforma_assumptions` | Pro forma assumptions | Rent growth, vacancy, loss to lease, concessions, other income and expense growth, hold and exit, as the model states them | Client's model | The model |
| `rent_comps` | Rent comparables | Subject and comps by bed / bath (units, avg SF, market and in-place rent, in-place rent per SF, occupancy); in-place rent chart for the unit types every property has | Radix rent comp set | `get_rent_comp_set`, `get_floor_plan_summary` (unitMixBath) per comp |

## Where blocks usually go

| Document | Blocks |
|---|---|
| Offering memorandum | All of them |
| BOV | Property snapshot, unit mix, rents vs. market, operating statement, rent comps (pricing blocks not built yet) |
| Investor or pitch deck | Property snapshot, actuals to pro forma, pro forma cash flow, assumptions |
| One-page teaser | Property snapshot, unit mix |

## Fixed design rules

- Money in whole dollars with thousands separators; negatives in parentheses. Changes in compact form (+$1.57M, -$679K).
- Percents to one decimal place.
- Unit types are labeled "1 bed / 1 bath", "Studio / 1 bath".
- Warm off-white page; charts and tiles sit on white cards with hairline borders.
- Titles and headline figures in a serif (Georgia); labels, tables and source lines in a sans (Arial). A small uppercase line above each title names the deal and the data date.
- Tables use horizontal hairlines only: uppercase header row over a dark rule, totals bold over a dark rule, NOI tinted with the brand's accent tint.
- Charts have no axis lines and light dashed gridlines; comparison series are warm greys so the subject stands out in the brand color.
- No footer, logo or slide number, so a block pastes cleanly into the user's own template.
- No monthly charts: OMs show periods side by side (years, T12, T3), and monthly NOI swings with when taxes and insurance are booked.
- Every derived figure (per unit, per SF, % of units, gap to market, expense ratio, growth, change) is named in the block's source line.

## Not in the catalog yet

- **Occupancy and rent trend** across the deal's rent rolls (needs 3 or more mapped rent rolls).
- **Lease expirations by month** from the rent roll.
- Sales comps, market overview, maps, and BOV pricing blocks (no Radix source yet).
