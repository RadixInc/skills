# Radix Skills

Agent skills for working with Radix MCP servers: ready-to-use workflows for AI agents.

Each skill is a folder with a `SKILL.md` that tells an agent which Radix MCP tools to use and how, so common tasks run the same way every time.

## Plugins

| Plugin | MCP server | Skills |
| --- | --- | --- |
| [`radix-underwriting`](plugins/underwriting) | Radix Underwriting (`https://underwriting-mcp.radix.com/mcp`) | [`plugins/underwriting/skills`](plugins/underwriting/skills) |

## Install

### Claude Code

```
/plugin marketplace add RadixInc/skills
/plugin install radix-underwriting@radix
```

The plugin includes the MCP server connection. Claude Code prompts you to authenticate the first time the server is used.

### Claude.ai and Claude Desktop

The [`underwriting-latest` release](https://github.com/RadixInc/skills/releases/tag/underwriting-latest) holds one zip per skill, for example `rent-roll-compare.zip`. Upload a zip under Customize > Skills. Zips don't include the server connection, so also add the Radix Underwriting server (`https://underwriting-mcp.radix.com/mcp`) as a connector in your Claude settings. `manifest.json` and `SHA256SUMS` in the release list every skill with its version and checksum.

### Other agents

Copy the skill folders you want from `plugins/<plugin>/skills/` into your agent's skills directory, and connect the matching MCP server yourself.

## Prerequisites

Access to the corresponding Radix MCP server for your organization. These skills do not grant access. Your Radix agreement and the MCP server's permissions still apply.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/authoring.md](docs/authoring.md). Design goals and the security model for this repository are in [docs/VISION.md](docs/VISION.md).

## License

Apache License 2.0. See [LICENSE](LICENSE). The license covers the contents of this repository. It does not grant access to Radix services and does not grant rights to Radix trademarks.
