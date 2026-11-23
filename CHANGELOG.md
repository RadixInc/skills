# Changelog

## Unreleased

- `ic-memo`: the page-head summary is now an investment overview (about 100 to 150 words) drafted with the analyst: discovery from the deal record, model and attached files first, depth set by whether there's a business plan (stabilized core deals get a short factual overview and no questions), at most 2 or 3 questions in one message, sources recorded in the run summary, approved text kept on reruns. Brand colors are kept readable (contrast guard), and the default disclaimer no longer calls the summary a draft.
- `deal-data-blocks` (new): Radix data as fixed, ready-to-paste blocks for the user's own OM, BOV or deck, in place of a generated OM. A catalog of eight blocks (property snapshot, unit mix by bed / bath, rents vs. market, operating history, operating statement or actuals to pro forma, pro forma cash flow, pro forma assumptions, rent comps), each with a fixed frame and design, as editable PowerPoint slides and PNGs, with an accuracy gate. No drafted text on any block.
- `ic-memo`: unit mix is now by bed / bath (unitMixBath).
- `ic-memo` (new): one-page IC memo as PDF and Word, led by the client's model and drawn with Radix components: page head and summary, deal metric tiles, NOI over the hold next to the T12 actual, capitalization, IRR sensitivity, T12/T3/T1 actuals next to the Year 1 pro forma with an analyst notes column. Ten fixed pre-send checks run before export and are reported to the analyst, not printed on the memo. Includes a brand profile (`radix.brand_profile/v1`, Radix house style by default), a deterministic renderer, and an accuracy gate that blocks export when figures don't reconcile.
- Release workflow: `<plugin>-latest` is now the ref the Claude plugin directory tracks. The workflow only moves it forward, fails if the move didn't land, and writes the result to the job summary. `docs/releasing.md` covers the directory webhook and how to check a release reached the directory.
## 1.0.2

- `radix-underwriting`: added `documentationUrl` (radix.com/mcp-underwriting) and `termsOfServiceUrl` to `plugin.json` for the directory listing, and linked documentation, privacy policy and terms from the plugin README.

## 1.0.1

- `radix-underwriting`: added a plugin README (skills, endpoint, what data goes where, install, support), an icon, and `privacyPolicyUrl`, so the plugin folder is self-contained for the Claude plugin directory. The plugin author and marketplace owner are now "Radix Software, Inc." Removed `skills/README.md`, whose links pointed outside the plugin folder.
- `occupancy-forecast`: falls back to partitioning by filters when the server won't page, and stops if the units returned don't match `totalUnits`. Checks whether notice to vacate is present on any unit and falls back to `moveOutDate` if not, reporting the basis used. Example removed.
- `rent-roll-compare`: notice-to-vacate handling now matches `occupancy-forecast` (use the field when present, otherwise the `moveOutDate` fallback). Dropped the version-specific `hasMissingLeaseStart` claim. Example removed.
- Both skills: ground rules are presented as the skill's own rules rather than attributed to the server's instructions.

## 1.0.0

- First release. The `radix-underwriting` plugin ships three skills: `expense-benchmark`, `occupancy-forecast` and `rent-roll-compare`.
- Release workflow: pushing a `<plugin>-vX.Y.Z` tag (for example `underwriting-v1.0.0`) publishes one uploadable zip per skill for that plugin, plus `manifest.json` and `SHA256SUMS`, and updates a rolling `<plugin>-latest` release with stable download URLs.
- Skill names must be unique across plugins.
- The plugin version now lives only in `plugin.json`. The validator rejects a version in the marketplace entry or in a skill's frontmatter.
