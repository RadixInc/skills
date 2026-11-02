# Vision

## Purpose

A public collection of agent skills that help Radix customers get useful work done with Radix MCP servers. Each skill packages a repeatable workflow (which tools to call, in what order, how to present the result) so a customer's AI agent does it consistently without the customer writing prompts from scratch.

Skills are grouped into one plugin per MCP server under `plugins/`. Today there is one: `underwriting`.

## Anti-goals

- Not a place for internal tooling, internal runbooks or employee-only workflows.
- Not a replacement for MCP server documentation. Skills describe workflows; tool reference lives with the server.
- Not a distribution channel for code that runs on its own. Skills may include small helper scripts, but the default is instructions only.
- Not a mirror of customer-specific configurations. Anything specific to one customer belongs in that customer's own setup.

## Security Model

This repository is public. Everything committed here is visible to anyone and stays in git history after removal.

- No secrets, tokens, API keys or credentials, including in examples.
- No internal hostnames or URLs. Only production MCP endpoints appear here. Dev and stage endpoints never do.
- No customer names, customer data or real borrower/applicant data. Examples use invented data.
- No internal ticket keys, internal Slack links or internal wiki links.
- Authentication is handled by the MCP server (OAuth or customer-issued credentials). Skills never ask the user to paste credentials into the conversation and never embed them.
- Skills must not instruct the agent to bypass the MCP server's access controls or to exfiltrate data to third-party services.
- Every change lands through a pull request with review. The validation workflow runs a secret scan on each PR.

## Distribution

- `plugins/<plugin>/skills/<name>/` is the only copy of each skill. The plugin and the downloadable zips are both built from it, never from a second copy.
- The plugin version lives only in `plugin.json`. A `vX.Y.Z` tag on `main` equal to that version publishes a GitHub Release with one Claude.ai-uploadable zip per skill. See [releasing.md](releasing.md).

## Open Questions

- Versioning once a second plugin ships: the repo-wide tag becomes ambiguous, so tags probably take a plugin prefix.
- When a second MCP server ships, whether skills that span servers live in their own plugin.
- Who owns review for each plugin (CODEOWNERS entries need GitHub handles).
