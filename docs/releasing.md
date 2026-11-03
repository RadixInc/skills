# Releasing

One directory, `plugins/<plugin>/skills/`, feeds both the Claude Code plugin and the downloadable zips. Both come from the same commit, so they can't disagree. Each plugin is released on its own, with its own version and its own tag.

## Where the version lives

Only in `plugins/<plugin>/.claude-plugin/plugin.json`. Don't set it in `.claude-plugin/marketplace.json` (Claude Code ignores it there when `plugin.json` has one) or in a skill's frontmatter. The validator fails on both. The release build stamps the plugin version into each zip's `SKILL.md` as `metadata.version`.

Claude Code users keep the cached copy of a plugin until its `version` string changes, so a change that customers should receive needs a version bump.

## Cut a release

1. Open a PR that sets the new version in the plugin's `plugin.json` and moves the `Unreleased` entries in `CHANGELOG.md` under that version. Merge it.
2. Tag the merge commit with `<plugin>-v<version>` and push the tag. `<plugin>` is the folder name under `plugins/`:
   ```
   git tag underwriting-v1.0.0 && git push origin underwriting-v1.0.0
   ```
3. The `release` workflow checks that the commit is on `main`, runs the validator, builds that plugin's zips and publishes a GitHub Release. It fails if the tag's plugin isn't in the marketplace or its version isn't the one in `plugin.json`.
4. The workflow then repoints the rolling release `<plugin>-latest` at the same commit and replaces its files.

Plugin folder names are lowercase kebab-case because they appear in tags. Skill names are unique across all plugins because they are zip names and download URLs; the validator enforces both.

## What a release contains

| File | Purpose |
| --- | --- |
| `<skill>.zip` | One per skill in that plugin. The zip holds the folder `<skill>/` with `SKILL.md` inside, the layout Claude.ai and Claude Desktop accept. |
| `manifest.json` | Each skill with its plugin, version, file name, sha256 and size. |
| `SHA256SUMS` | Checksums for the zips. |

Zips are reproducible: the same commit yields byte-identical files.

## Linking from the website

Link to the rolling release. Its URLs don't change between versions, and each plugin has its own:

```
https://github.com/RadixInc/skills/releases/download/underwriting-latest/<skill>.zip
https://github.com/RadixInc/skills/releases/download/underwriting-latest/manifest.json
```

A new plugin gets its own `<plugin>-latest` on its first release, with no website change to existing links. Don't use GitHub's `releases/latest`. It is a single repo-wide pointer, so with several plugins it can sit on any plugin's versioned release. The workflow passes `--latest=false`, but GitHub still showed `underwriting-v1.0.0` as the latest release after the first run.

Zips don't carry the server connection that the plugin bundles in `.mcp.json`. The download page needs to tell people to add the Radix Underwriting server (`https://underwriting-mcp.radix.com/mcp`) as a connector in Claude.

## Tag rules

A repository ruleset, "Release tags", covers tags matching `*-v<digit>*` (for example `underwriting-v1.0.0`). Only the repository Admin role can create, move or delete them. Everyone else with write access is blocked, so a release can't be started from an unreviewed branch.

The ruleset deliberately doesn't match `<plugin>-latest`, so the release workflow can create and repoint those tags with its own token. The pattern requires a digit after `-v`, so a plugin such as `rent-vault` isn't caught by accident. Don't widen the pattern to `*-v*`.

A tag can only be re-used after an Admin deletes it, so a failed release is retried by deleting the tag and pushing it again.

## Build locally

```
python3 scripts/build_skill_zips.py --out dist                        # every plugin, as CI does on each PR
python3 scripts/build_skill_zips.py --out dist --tag underwriting-v1.0.0   # one plugin, as the release does
```
