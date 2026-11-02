# Changelog

## Unreleased

## 1.0.0

- First release. The `radix-underwriting` plugin ships three skills: `expense-benchmark`, `occupancy-forecast` and `rent-roll-compare`.
- Release workflow: pushing a `<plugin>-vX.Y.Z` tag (for example `underwriting-v1.0.0`) publishes one uploadable zip per skill for that plugin, plus `manifest.json` and `SHA256SUMS`, and updates a rolling `<plugin>-latest` release with stable download URLs.
- Skill names must be unique across plugins.
- The plugin version now lives only in `plugin.json`. The validator rejects a version in the marketplace entry or in a skill's frontmatter.
