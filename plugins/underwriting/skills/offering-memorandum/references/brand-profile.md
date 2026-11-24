# Brand profile (`radix.brand_profile/v1`)

One JSON document per account (optionally per user) that every Radix deal document reads: IC memo, OM, BOV and template push. It is a plain JSON file the user keeps, so the same file works in any agent.

## Fields

| Field | Type | Notes |
|---|---|---|
| `schema` | string | Always `radix.brand_profile/v1` |
| `profile_id` | string | Stable id |
| `name` | string | Shown to the user ("Acme Capital brand") |
| `owner.level` | `default` \| `account` \| `user` | User profiles override account profiles |
| `logo.data_uri` | string \| null | PNG or SVG as a data URI, max 500 KB. Preferred, so the file is self-contained |
| `logo.url` | string \| null | Alternative to `data_uri` when stored by the server |
| `logo.wordmark_text` | string | Shown when there's no logo |
| `colors.primary` | hex | Header band and section headings |
| `colors.accent` | hex | Rules, markers, highlights |
| `colors.accent_tint` | hex | Snapshot tiles, NOI row, grid headers. Keep it light |
| `fonts.heading`, `fonts.body` | string | From the approved list. v1: `Manrope` |
| `firm.display_name` | string | Used in headers and file names |
| `firm.contact_lines` | string[] | Broker team for the OM and BOV contact pages, one line each ("Jane Doe, Senior Managing Director · jane@firm.com · 602 555 0100") |
| `disclaimer` | string | Client-owned text for the IC memo footer, printed verbatim |
| `defaults.ic_memo.layout` | `editorial` \| `cards` | IC memo page layout; editorial is the default |
| `om_disclaimer` | string | Client-owned confidentiality and disclaimer text for the OM's last page, printed verbatim |
| `defaults.<doc>.format` | IC memo: `pdf` \| `docx` \| `pdf+docx`. Data blocks: `pptx` \| `png` \| `pptx+png`. OM: `pptx` \| `pdf` \| `pptx+pdf`. Or null | Null means ask every run. `<doc>` is `ic_memo`, `data_blocks` or `om` |
| `defaults.ic_memo.variant` | `one_pager` \| `full` | |
| `defaults.ic_memo.waterfall` | `auto` \| `always` \| `never` | Equity waterfall on the IC memo. `auto` shows it when the model has one |
| `updated_at` | date | |

## What the client can and can't change

- **Can:** logo, the three brand colors, font pair from the approved list, firm name and contacts, disclaimer, default formats.
- **Can't:** layout, type scale, neutral colors, table design, number formats. Those keep every output looking finished.

## Color roles to show the user

When asking for brand colors, list them by role so the user knows where each appears:

| Role | IC memo | Data blocks | OM |
|---|---|---|---|
| **Primary** | Wordmark, NOI bars, base-case cell | Main chart bars, snapshot figures, the subject property in comparison charts | Cover and section divider background, highlight markers, plus everything the data blocks use it for |
| **Accent** | Heading markers and rules | Second chart series (in-place rent, revenue) | Title rule on every slide, plus the data blocks' uses |
| **Accent tint** | Pro forma column, highlighted rows | NOI rows, the subject property's rows in the comps table (keep it very light) | Offering terms panel, plus the data blocks' uses |

The users can give colors as hex codes in chat; the agent writes them into `brand.json`.

The renderers check contrast so a brand can't make figures hard to read: a primary or accent lighter than 3:1 against white is darkened until it passes, and an accent tint darker than a light tint is lightened. The run summary says when a color was adjusted.

## Where it's stored

The skills ship on their own, with nothing stored in Radix:

1. **A `brand.json` the user attaches**, or colors they give in chat. When the user gives colors or a default format, the agent writes `brand.json` (starting from `assets/brand-radix-default.json`) and sends it back so they can keep it. In a Claude Project, adding `brand.json` to the project files makes every chat in the project use it.
2. **`assets/brand-radix-default.json`**, the Radix house style, when the user has none.

Storing the profile in Radix so it follows the account (`get_brand_profile` / `save_brand_profile` on the MCP) is planned, not built. Don't call those tools unless the MCP lists them.
