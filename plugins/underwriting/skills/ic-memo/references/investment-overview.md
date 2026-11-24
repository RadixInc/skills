# Investment overview

The short paragraph at the top of the memo. It orients the reader in two sentences and points to the plan; everything else on the page carries the detail.

- **Length**: about 30 to 60 words, two sentences, at most three.
- **Sentence 1, the basics**: what is being bought and how (property type, location, all cash or financed, hold). Keep it plain; the header already shows the address, units, vintage and square feet.
- **Sentence 2, the plan at a high level**: the strategy in a committee's words, taken from the investment thesis ("a value-add plan to renovate most of the units and lease up the vacancy", "a core hold with no business plan", "a lease-up of a new delivery").
- **Optional third sentence**: only if the analyst gave a reason the opportunity exists (a seller's situation, an operator edge), attributed to them.

## What to leave out

- Figures the page already shows: price, required equity, IRR, multiple, cap rates, NOI, occupancy, rents. The overview shouldn't make the reader read the same number twice.
- The value drivers and what the plan depends on: those are the thesis card's job ([investment-thesis.md](investment-thesis.md)).
- Adjectives the data doesn't support, and any thesis the model or the analyst didn't give you. If the model has no plan, say so plainly ("The model has no business plan beyond holding the property as is").

## Questions

The overview doesn't need its own questions. It takes the strategy from the thesis, so it follows whatever the analyst confirms there. If they correct the strategy, rewrite the second sentence to match.

## Finishing

- Set `commentary.status` to `approved` once the analyst accepts it, and keep it on reruns unless the thesis changes.
- Record where the plan statement came from in `commentary.sources` (the thesis, the model, the analyst). Sources go in the run summary, not on the memo.
- Any figure you do use must appear on the page exactly as printed (the gate checks).

Example:

> Harbor Point is a garden-style property in Phoenix, bought with agency debt for a 5-year hold. The plan is value-add: renovate most of the units and lease up the vacancy.
