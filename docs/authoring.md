# Authoring skills

## Add a skill

1. Copy `templates/skill/` to `plugins/<plugin>/skills/<skill-name>/`.
2. Edit `SKILL.md`. The `name` in the frontmatter must equal the folder name (lowercase kebab-case).
3. Run `python3 scripts/validate_skills.py`.
4. Open a pull request. Bump the plugin version in `plugins/<plugin>/.claude-plugin/plugin.json` and in `.claude-plugin/marketplace.json` when the change is customer-visible.

## Layout of a skill

```
<skill-name>/
├── SKILL.md        # required: frontmatter + instructions
├── references/     # optional: longer docs the agent reads when needed
└── scripts/        # optional: helper scripts, kept small and reviewed carefully
```

## Writing the description

The `description` decides whether the agent picks the skill. Say what the skill does and when to use it, and include the words a customer is likely to use and the MCP tools involved. Keep it under 1024 characters.

## Referring to MCP tools

- Use the tool name as the server exposes it (for example `search_loans`), without a client-specific prefix. Clients add their own prefixes, such as `mcp__<server>__`.
- State the MCP server as a prerequisite in the skill.
- Say what the agent should do when a tool returns an error, an empty result or a permissions failure.

## Keeping SKILL.md focused

Put the core workflow in `SKILL.md` and move long reference material to `references/`, linked from `SKILL.md`, so it loads only when needed.

## Public repository rules

See the Security Model in [`VISION.md`](VISION.md). In short: no secrets, no internal URLs or ticket keys, no customer data, production endpoints only.
