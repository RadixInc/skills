# Changelog

## Unreleased

## 1.0.0

- First release. The `radix-underwriting` plugin ships three skills: `expense-benchmark`, `occupancy-forecast` and `rent-roll-compare`.
- Release workflow: pushing a `vX.Y.Z` tag publishes one uploadable zip per skill, plus `manifest.json` and `SHA256SUMS`.
- The plugin version now lives only in `plugin.json`. The validator rejects a version in the marketplace entry or in a skill's frontmatter.
