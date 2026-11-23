# Block catalog

Every block has the same frame: the block title, a subject line (deal name and the data's date or period), the content, and a source line. The content below is fixed for each block; only the brand's three colors change.

| Block id | Title on the block | What it shows | Source | Needs |
|---|---|---|---|---|
| `property_snapshot` | Property snapshot | 8 tiles: units, year built, average unit size, occupancy, vacant units, average market rent, average in-place rent, in-place as % of market | Radix deal record and rent roll | `get_deal_details`, `get_deal_summary`, `get_floor_plan_summary` (unitMixBath) |
| `unit_mix` | Unit mix | Table by bed / bath: units, % of units, avg SF, market rent, in-place rent, market rent per SF, occupied; total row; units by unit type bar chart | Radix rent roll | `get_floor_plan_summary` (unitMixBath) |
| `rents_vs_market` | Rents vs. market | Market, in-place and last-90-days lease rent by bed / bath (chart and table), in-place as % of market | Radix rent roll | `get_floor_plan_summary` (unitMixBath) |
| `operating_history` | Operating history | Monthly EGR, OpEx and NOI over the T12 (line chart); T12, T3 and T1 annualized totals and NOI per unit | Radix operating statement | `get_operating_statement` (monthly, 12-month window) |
| `operating_statement` | Operating statement, or Actuals to pro forma with the model | T12, T3 and T1 annualized by revenue and expense group; with the client's model, the Year 1 pro forma, per unit and change vs. T12 | Radix operating statement, client's model | `get_operating_statement`; the model |
| `proforma_cash_flow` | Pro forma cash flow | EGR, OpEx and NOI by year over the hold, NOI bar chart | Client's model | The model |
| `proforma_assumptions` | Pro forma assumptions | Rent growth, vacancy, loss to lease, concessions, other income and expense growth, hold and exit, as the model states them | Client's model | The model |
| `rent_comps` | Rent comparables | Subject and comps by bed / bath (units, avg SF, market and in-place rent, occupancy); in-place rent chart for the unit types every property has | Radix rent comp set | `get_rent_comp_set`, `get_floor_plan_summary` (unitMixBath) per comp |

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
- Totals and NOI rows are bold; NOI is tinted with the brand's accent tint.
- No footer, logo or slide number, so a block pastes cleanly into the user's own template.
