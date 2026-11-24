# Investment overview

The paragraph at the top of the memo. It tells the committee what the opportunity is, why it exists, how the plan creates value, and the one consideration that matters most. About 100 to 150 words, written as a narrative, not a list of metrics.

The goal is that the analyst gets a usable overview by reading one proposed paragraph and making a brief correction or pointing you to a file, not by filling in a questionnaire.

The investment thesis card next to the deal metrics carries the strategy and sized drivers ([investment-thesis.md](investment-thesis.md)). The overview tells the story around it; don't repeat the drivers word for word. Ask the thesis and overview questions together, in one round.

## 1. Decide how deep to go

The depth depends on whether there's a business plan to explain.

- **Business plan deal** (value-add, renovation, lease-up, repositioning, operational turnaround, or the model shows renovation capex, a renovation premium, or occupancy or rent moving well above the T12): the thesis is the plan, so it's worth getting right. Run steps 2 to 4 and ask if something material is missing.
- **Stabilized core or core-plus deal** (high occupancy, in-place rents near market, no renovation budget, flat assumptions): there is little to explain. Write a short factual overview (what it is, where, how it's performing, how it's financed and held) and don't ask questions. The analyst can add a thesis if they want one.
- **Can't tell**: write the factual overview and ask one question, whether there's a business plan.

Never infer a business plan from a favorable pro forma alone. A model that shows NOI growing is a projection, not a thesis.

## 2. Use what's already there

Before asking anything, look at what you have:

- The deal record in Radix (comments, deal type, asset and location quality, status).
- The client's model: renovation budget, renovation premium, rent growth, occupancy path, hold and exit.
- Files the user attached or pointed to (OM, deal notes, broker emails), and anything said earlier in the conversation.

Look for:

- **Opportunity**: what is being acquired and what makes it attractive.
- **Thesis**: why the opportunity exists (a seller's situation, below-market rents, mismanagement, a market tailwind).
- **Business plan**: renovations, operational changes, lease-up or repositioning.
- **Key consideration**: the material risk, dependency or uncertainty for execution.

Keep track of where each point came from, in four kinds: documented fact (Radix data, a signed document), model assumption, third-party claim (an OM or broker material), and your inference.

When the user names a document, folder, link or connected app, read it with the tools you have and take only what the overview needs. Don't run broad searches and don't ask the user to copy text you can retrieve yourself.

## 3. Ask only what matters

If something material is missing (for a business plan deal), propose your reading and ask to confirm or correct it, in one message:

- At most 2 or 3 targeted questions, combined where they're related.
- Don't ask for figures already in the model, and don't ask the user to confirm every sourced fact.
- Accept plain answers, corrections, or a pointer to another file. If they point to a file, read it and update your reading before asking anything else.
- If what you have is enough, skip the question and write the overview.

Example:

> From the model and the rent roll, this reads as a value-add acquisition: occupancy is 76% and in-place rents are 89% of market, and the plan brings both up. I didn't find a renovation scope or what sets the property apart from its comps. Is that the strategy? You can also point me to the OM or deal notes.

## 4. Write it

- Lead with the opportunity and why it's compelling, then the main value-creation strategy, then market or asset-specific support, then the most consequential execution consideration when known.
- Don't repeat the metrics the page already shows (required equity, IRR, multiple, cap rates) unless one directly supports the thesis. Any figure you use must be printed on the page, as the page prints it (the gate checks).
- Use neutral language for anything not supported by a source. Attribute claims from marketing material you haven't verified ("the broker cites...").
- Plain language. No adjectives the data doesn't support.

## 5. Finish

- Don't hold the memo for optional information. If the rationale is still incomplete, write a factual overview without a thesis.
- Show the paragraph and let the analyst approve or edit it. Set `commentary.status` to `approved` once they do.
- Record where each point came from in `commentary.sources`. Sources go in the run summary, not on the memo.
- Once approved, keep the paragraph on later reruns unless the user revises it or new information changes it.
