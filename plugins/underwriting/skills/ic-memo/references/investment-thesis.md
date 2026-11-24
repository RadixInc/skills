# Investment thesis

The card next to the deal metrics. It tells the committee, at a glance, what kind of deal this is and what has to go right:

- **Strategy**: one specific line, for example "Value-add: interior renovation and lease-up", "Core-plus: mark-to-market on expiring leases", "Lease-up of a new delivery". Not "good location, growing market".
- **Strategy detail**: one line with the scale and timing ("Renovate 400 of 555 units over 36 months").
- **2 to 4 value drivers**, each a short title and one sentence **sized in dollars, units, percentages or months** and tied to a line in the model ("400 units at $12,500 each ($5.0M) over 36 months"), not an adjective ("full interior renovation").
- **What the plan depends on**: the one assumption the returns rest on, sized ("Most of the NOI growth from Year 1 to Year 3 depends on the $175 premium on all 400 units").

## Best practices this follows

- **Specific, so the committee knows the deal type immediately.** Name the strategy in the words a committee uses: core, core-plus, value-add, opportunistic, lease-up, development.
- **Every driver ties to the underwriting.** A business plan is a budget line, a unit count and a timeline, not a description. Every number traces to a model cell or a document.
- **Consistent with the rest of the memo.** The thesis can't name one strategy while the model assumes another; a renovation thesis needs a renovation budget, a lease-up thesis needs an occupancy path, a rent-growth thesis needs rent growth. If they don't line up, say so in the draft and ask.
- **Name the dependency.** Committees want the single assumption that carries the returns, sized. If the exit cap is below the going-in cap, the returns lean on cap rate compression: say that.
- **Why us, why now.** The model can show what the plan is; it can't show the operator's edge or why the opportunity exists. Ask for it.

## 1. Read the strategy from the model

Read how the model is set up before writing anything. In the Radix underwriting model export (see [client-model.md](client-model.md)):

| Signal | Where | Points to |
|---|---|---|
| Units to be renovated, cost per unit, rent bump, downtime | `Input` unit renovation block (rows 86 to 109: `D` cost, `E` rent bump, `F` post-renovation rent, `G:J` units by year, `G107` downtime) | Value-add. Aggressive when most units are renovated, cost is high per unit, the bump is a large share of in-place rent, or the schedule is fast |
| Projected capital expenditures, property-wide capex | `Input!F42`, `Input` rows from 200 | Capital plan (value-add or deferred maintenance) |
| Vacancy path | `Input` rows 114 and 121 to 124 | Lease-up when vacancy falls well below today's; stabilized when it's flat at a low level |
| Loss to lease path | `Input` row 116 | Mark-to-market when it burns off |
| Market rent growth | `Input` rows 78 to 82 | Rent-growth play when above the market, flat when 0% |
| Expense lines vs. the T12 | `Property CF` Year 1 vs. the Radix T12 | Operational play when payroll, repairs or utilities drop meaningfully |
| Other income vs. the T12 | `Property CF` Year 1 | New income programs (utility billing, fees) |
| Leverage, interest-only, hold | `Sources & Uses`, `Summary` | Opportunistic with high leverage and a short hold; core with low leverage and a long hold |
| Exit cap vs. going-in cap | `Summary` | Compression dependency when the exit cap is below the going-in |

Other models: find the same inputs by label. Record every cell you used in `thesis.signals` and each driver's `sources`.

Classify the deal from the signals, then size 2 to 4 drivers from the cells. If the model has no plan at all (no renovations, flat occupancy and rents), say that plainly as the strategy ("No business plan in the model") and let the drivers describe what the model does assume. Don't invent a plan.

## 2. Ask the analyst to verify

Combine this with the investment overview's single round of questions (at most 2 or 3 in total). Show the strategy and drivers as you read them and ask:

> From the model, this reads as a value-add deal: 400 of 555 units renovated at $12,500 each over 36 months for a $175 premium, with occupancy going from 76% to 94% by Year 2. The returns mostly depend on the premium. Is that the plan? And what's your edge on this one (why this deal, why now)?

- If the analyst corrects the strategy, rebuild the drivers from the model with their reading, and flag any place where the model and their plan disagree.
- If they give the edge or the reason the opportunity exists, use it in the investment overview, attributed to them.
- If they don't answer, render the draft and list the thesis as unconfirmed in the reply.

Set `thesis.status` to `confirmed` once they agree. Keep a confirmed thesis on reruns unless the model or the user changes it.

## 3. Relationship to the investment overview

The overview at the top tells the story in prose (the opportunity, why it exists, the main consideration). The thesis card is the structured version: strategy, sized drivers, dependency. Don't repeat the drivers word for word in the overview.
