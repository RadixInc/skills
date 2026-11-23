# Brand profile (`radix.brand_profile/v1`)

One JSON document per account (optionally per user) that every Radix deal document reads: IC memo, OM, BOV and template push. It is plain JSON so it works the same in any agent and in the Radix app.

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
| `firm.contact_lines` | string[] | For OM and BOV contact pages |
| `disclaimer` | string | Client-owned text, printed in the footer verbatim |
| `defaults.<doc>.format` | `pdf` \| `docx` \| `pdf+docx` \| `pptx` \| null | Null means ask every run |
| `defaults.ic_memo.variant` | `one_pager` \| `full` | |
| `defaults.ic_memo.waterfall` | `auto` \| `always` \| `never` | Equity waterfall on the IC memo. `auto` shows it when the model has one |
| `updated_at` | date | |

## What the client can and can't change

- **Can:** logo, the three brand colors, font pair from the approved list, firm name and contacts, disclaimer, default formats.
- **Can't:** layout, type scale, neutral colors, table design, number formats. Those keep every output looking finished.

## Color roles to show the user

When asking for brand colors, list them by role so the user knows where each appears:

1. **Primary**: header band, section headings
2. **Accent**: heading markers and rules
3. **Accent tint**: tiles, highlighted rows, grid headers (a very light version of the accent)

The renderer checks contrast: if white text on the primary color is under 4.5:1, it uses dark text instead.

## Where it's stored

1. **Radix MCP** (`get_brand_profile` / `save_brand_profile`), when available. This is the source of truth, so a profile saved from one agent shows up in every agent and in the app.
2. **A `brand.json` file** the user keeps and attaches, when the MCP doesn't offer the tools yet.
3. **`assets/brand-radix-default.json`**, the Radix house style, when neither exists.
