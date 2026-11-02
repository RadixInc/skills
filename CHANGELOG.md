# Changelog

## Unreleased

- `occupancy-forecast`: falls back to partitioning by filters when the server won't page, and stops if the units returned don't match `totalUnits`. Checks whether notice to vacate is present on any unit and falls back to `moveOutDate` if not, reporting the basis used. Example removed.
- `rent-roll-compare`: notice-to-vacate handling now matches `occupancy-forecast` (use the field when present, otherwise the `moveOutDate` fallback). Dropped the version-specific `hasMissingLeaseStart` claim. Example removed.
- Both skills: ground rules are presented as the skill's own rules rather than attributed to the server's instructions.

## 1.0.0

- First release. The `radix-underwriting` plugin ships three skills: `expense-benchmark`, `occupancy-forecast` and `rent-roll-compare`.
- Release workflow: pushing a `<plugin>-vX.Y.Z` tag (for example `underwriting-v1.0.0`) publishes one uploadable zip per skill for that plugin, plus `manifest.json` and `SHA256SUMS`, and updates a rolling `<plugin>-latest` release with stable download URLs.
- Skill names must be unique across plugins.
- The plugin version now lives only in `plugin.json`. The validator rejects a version in the marketplace entry or in a skill's frontmatter.
