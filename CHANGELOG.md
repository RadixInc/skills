# Changelog

## Unreleased

- `deal-data-blocks`: new skill. Radix data as fixed, ready-to-paste blocks for the user's own OM, BOV or deck: property snapshot, unit mix by bed / bath, rents vs. market, operating history, actuals to pro forma, pro forma cash flow and assumptions, rent comps. Editable PowerPoint slides and PNGs, an accuracy gate, no drafted text on any block.
- `offering-memorandum`: new skill. Full OM deck (PowerPoint and PDF) built as a recipe over the same blocks, plus the OM's own pages: cover, executive summary and offering terms, property overview and photos, sales comps, market overview and contacts. Drafted summary and highlights are gated so they only cite figures the deck prints.
- `scripts/validate_skills.py`: fails when files the two skills share (`blocks_lib.js`, references, brand default) drift apart.

## 1.0.3

- `create-deal-from-docs`: new skill. Creates a deal from an OM, flyer, broker email, property website link, or a rent roll and T12 alone, uploads any rent roll or T12 to the new deal in the same run, and reports each field with its source. Asks once whether it may look up missing details on the web (property website, management company, broker contact, asset quality, amenities, year built), using only the property name and address. Never writes to deal comments or fills the buyer's own pricing and returns fields.
- `radix-underwriting` README: lists the new skill and describes the deal writes, uploads and optional web lookup.
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
