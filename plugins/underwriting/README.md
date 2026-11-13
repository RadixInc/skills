# Radix Underwriting

Skills for the Radix Underwriting MCP server. The plugin connects Claude to the server and adds three ready-made workflows for multifamily underwriting, so the agent runs each analysis the same way every time without you writing the prompt.

You need access to the Radix Underwriting MCP server through your organization's Radix agreement. The plugin does not grant access. Your Radix account and the server's permissions still apply.

## Skills

| Skill | What it does |
| --- | --- |
| `expense-benchmark` | Compares a deal's operating expenses (T12 actuals or an underwritten budget) with its 10 closest comparable deals in your account. Shows each expense category per unit next to the comp weighted average, median and range, and lists categories outside the range. |
| `occupancy-forecast` | Builds a 30/60/90-day occupancy view from the latest rent roll, using only committed changes: signed future leases, notices to vacate, and backfilled vacant units. Lease expirations with no confirmed outcome are listed separately. |
| `rent-roll-compare` | Compares two rent rolls for the same deal and reports what changed, unit by unit: occupancy, move-ins and move-outs, renewals versus new leases, lease trade-out, concessions, month-to-month and notice exposure. |

Claude uses a skill when your request matches it, for example "how do this property's expenses compare to comps?", "what will occupancy look like next quarter?", or "what changed since the last rent roll?".

## What the plugin connects to

The plugin declares one remote MCP server in `.mcp.json`:

| Server | Endpoint |
| --- | --- |
| Radix Underwriting | `https://underwriting-mcp.radix.com/mcp` |

The skills tell Claude to call this server's tools to find a deal and read its details, operating statements, expense comp sets, rent roll units and floor plan summaries. Deal data is sent between Claude and the Radix server in those calls. The skills do not send data to any other service.

The plugin contains no hooks, scripts, executables or package installs. It is Markdown instructions plus the server connection.

## Install

In Claude Code:

```
/plugin marketplace add RadixInc/skills
/plugin install radix-underwriting@radix
```

The first time a skill uses the server, Claude Code prompts you to authenticate with your Radix credentials. The skills never ask you to paste credentials into the conversation.

For Claude.ai and Claude Desktop, the same skills are available as one zip per skill from the [`underwriting-latest` release](https://github.com/RadixInc/skills/releases/tag/underwriting-latest). Upload each zip under Customize > Skills, and add the server endpoint above as a connector.

## How the skills report results

- Figures come from the server as returned. The skills report them and label any figure they derive, such as a difference from the comp median.
- The skills report where a deal sits relative to its comps. They don't recommend underwriting adjustments unless you ask.
- Deal names, line item names and comments come from Radix users and uploaded files. The skills treat them as data and never follow them as instructions.
- If a deal name matches more than one deal, Claude asks which one you mean.

## Documentation, support and legal

- Documentation for the Radix Underwriting MCP server, including setup and the full tool list: [radix.com/mcp-underwriting](https://radix.com/mcp-underwriting/)
- Report problems with the skills at [github.com/RadixInc/skills/issues](https://github.com/RadixInc/skills/issues). Report security issues, including issues with the Radix MCP server, to security@radix.com and not in a public issue.
- [Privacy policy](https://radix.com/privacy-policy/) and [terms of service](https://radix.com/terms-of-services/)

## License

Apache License 2.0. The license covers the contents of this plugin. It does not grant access to Radix services or rights to Radix trademarks.
