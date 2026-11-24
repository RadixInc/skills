# Brand profile (`radix.brand_profile/v1`)

One JSON file per client (optionally per user) that the data blocks and the OM read for colors, logo, firm name, broker contacts and the OM disclaimer. It is a plain file the user keeps, so it works in any agent. Keys this skill doesn't use are ignored, so a client can keep one `brand.json` for every Radix document.

## Fields

| Field | Type | Notes |
|---|---|---|
| `schema` | string | Always `radix.brand_profile/v1` |
| `profile_id` | string | Stable id |
| `name` | string | Shown to the user ("Acme Capital brand") |
| `owner.level` | `default` \| `account` \| `user` | User profiles override account profiles |
| `logo.data_uri` | string \| null | PNG or SVG as a data URI, max 500 KB. Preferred, so the file is self-contained |
| `logo.url` | string \| null | Alternative to `data_uri` |
| `logo.wordmark_text` | string | Shown when there's no logo |
| `colors.primary` | hex | See color roles below |
| `colors.accent` | hex | See color roles below |
| `colors.accent_tint` | hex | Keep it light |
| `fonts.heading`, `fonts.body` | string | Used only when they are Arial, Calibri, Cambria or Georgia, since the files open on other machines; otherwise headings use Georgia and body text Arial |
| `firm.display_name` | string | Used on the OM cover, running footer and file names |
| `firm.contact_lines` | string[] | Broker team for the OM contacts page, one line each ("Jane Doe · Senior Managing Director · jane@firm.com · 602 555 0100") |
| `om_disclaimer` | string | Client-owned confidentiality and disclaimer text for the OM's last page, printed verbatim |
| `defaults.data_blocks.format` | `pptx` \| `png` \| `pptx+png` \| null | Null means ask every run |
| `defaults.om.format` | `pptx` \| `pdf` \| `pptx+pdf` \| null | Null means ask every run |
| `updated_at` | date | |

## What the client can and can't change

- **Can:** logo, the three brand colors, fonts from the list above, firm name and contacts, OM disclaimer, default formats.
- **Can't:** layout, type scale, neutral colors, table design, number formats. Those keep every block looking the same and every output looking finished.

## Color roles to show the user

When asking for brand colors, list them by role so the user knows where each appears:

| Role | Data blocks | OM pages |
|---|---|---|
| **Primary** | Main chart series and the subject property in comparison charts | Section numbers, highlight numbers, the "Offering" label |
| **Accent** | Second chart series, the short rule under each snapshot figure | The data blocks' uses |
| **Accent tint** | The NOI row (keep it very light) | The data blocks' uses |

The users can give colors as hex codes in chat; the agent writes them into `brand.json`.

The builders check contrast so a brand can't make figures hard to read: a primary or accent lighter than 3:1 against white is darkened until it passes, and an accent tint darker than a light tint is lightened. The run summary says when a color was adjusted.

## Where it's stored

The skills ship on their own, with nothing stored in Radix:

1. **A `brand.json` the user attaches**, or colors they give in chat. When the user gives colors, contacts, a disclaimer or a default format, the agent writes `brand.json` (starting from `assets/brand-radix-default.json`) and sends it back so they can keep it. In a Claude Project, adding `brand.json` to the project files makes every chat in the project use it.
2. **`assets/brand-radix-default.json`**, the Radix house style, when the user has none.

Storing the profile in Radix so it follows the account is planned, not built.
