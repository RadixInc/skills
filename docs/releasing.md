# Releasing

One directory, `plugins/<plugin>/skills/`, feeds both the Claude Code plugin and the downloadable zips. Both come from the same commit, so they can't disagree.

## Where the version lives

Only in `plugins/<plugin>/.claude-plugin/plugin.json`. Don't set it in `.claude-plugin/marketplace.json` (Claude Code ignores it there when `plugin.json` has one) or in a skill's frontmatter. The validator fails on both. The release build stamps the plugin version into each zip's `SKILL.md` as `metadata.version`.

Claude Code users keep the cached copy of a plugin until its `version` string changes, so a change that customers should receive needs a version bump.

## Cut a release

1. Open a PR that sets the new version in `plugin.json` and moves the `Unreleased` entries in `CHANGELOG.md` under that version. Merge it.
2. Tag the merge commit and push the tag:
   ```
   git tag v0.2.0 && git push origin v0.2.0
   ```
3. The `release` workflow checks that the commit is on `main`, runs the validator, builds the zips and publishes a GitHub Release. It fails if the tag doesn't equal the `plugin.json` version.

While there is one plugin, the repo-wide tag `vX.Y.Z` is that plugin's version. When a second plugin ships, switch to prefixed tags (`underwriting-v0.2.0`) and have the website read `manifest.json` from a specific release.

## What a release contains

| File | Purpose |
| --- | --- |
| `<skill>.zip` | One per skill. The zip holds the folder `<skill>/` with `SKILL.md` inside, the layout Claude.ai and Claude Desktop accept. |
| `manifest.json` | Each skill with its plugin, version, file name, sha256 and size. |
| `SHA256SUMS` | Checksums for the zips. |

Zips are reproducible: the same commit yields byte-identical files.

## Linking from the website

Stable link to the newest zip: `https://github.com/RadixInc/skills/releases/latest/download/<skill>.zip`. To show versions, fetch `https://github.com/RadixInc/skills/releases/latest/download/manifest.json`.

Zips don't carry the server connection that the plugin bundles in `.mcp.json`. The download page needs to tell people to add the Radix Underwriting server (`https://underwriting-mcp.radix.com/mcp`) as a connector in Claude.

## Build locally

```
python3 scripts/build_skill_zips.py --out dist
```
