# Pre-send checks

Pre-send checks are fixed rules the renderer runs on the memo's data before it goes to committee. They are for the analyst, not the committee: they are never printed on the memo. They appear in the renderer's output, in the run summary, and in the agent's reply, so the analyst can fix a data problem or prepare an answer before sending. The same data gives the same checks on every run and in every agent.

A rule only runs when its inputs exist (no model, no pro forma rules).

| Check | Fires when | Inputs |
|---|---|---|
| Pro forma revenue well above actual | Y1 EGR is more than 10% above T12 EGR | actuals, proforma |
| Pro forma NOI well above actual | Y1 NOI is more than 15% above T12 NOI | actuals, proforma |
| Other income dropped in pro forma | Y1 other income is under half of T12 other income | actuals, proforma |
| Low occupancy | Rent roll occupancy is under 90% | snapshot |
| Near-term expirations | Leases expiring in the next 90 days exceed 10% of units | snapshot |
| NOI falls over the hold | Final-year NOI is below Year 1 NOI | hold_cash_flow |
| Exit cap at or below going-in | Exit cap is at or below the cap rate on T12 NOI | returns, deal_terms, actuals |
| Expense line running hot | Any expense line's T3 annualized is 25% or more above its T12 (lines over $10,000) | actuals |
| T12 rent doesn't match the rent roll | T12 potential rent per unit per month differs from rent roll market rent by more than 20% | actuals, snapshot |
| Thin debt coverage | Minimum DSCR is under 1.25x | hold_cash_flow |

Thresholds live in `scripts/render_memo.py` (`risk_flags`). Change them there and here together.

Checks state what the data shows. They don't say whether the plan is wrong: a value-add pro forma is supposed to sit above the T12. When a check points at a pro forma line, the analyst can explain it in that line's note (`proforma.notes`), which does print on the memo.

Some checks point at data quality rather than the deal (for example, T12 rent that doesn't match the rent roll usually means a mapping or upload issue). Those should be fixed in Radix before the memo is sent.
