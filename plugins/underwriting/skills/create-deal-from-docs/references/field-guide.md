# Field guide

"Report as" is the plain English name to use in the report. Use these names exactly, so every report reads the same.

## From the user's sources only (blank if not stated)

| Report as | API field | What to enter | Notes |
|---|---|---|---|
| Deal name | dealName | The property's marketed name | If the OM uses a project code name, use it and mention it in the report so the user can rename |
| Address | address, address2, city, state, zip | The property's street address | Several addresses: use the leasing office or primary address and mention the others in the report. If no source has it, the web setting is on, and you have the name plus city or state, you may look it up on the property's own website or the county property record; use it only if the name and city match |
| Units | unitCount | Total units as stated in the marketing material, website | If an attached rent roll differs, keep the stated figure; the difference usually means the rent roll parsed poorly, so note it. With only a rent roll, use its stated total; if it has none, count the distinct units it lists and say so in the source |
| Rentable square feet | residentialSquareFootage | Net rentable residential square feet | Not gross building area, not retail. If only average unit size is given, leave blank |
| Buildings | noOfBuildings | Number of residential buildings | |
| Stories | noOfStories | Stories of the tallest building | |
| Floor plans | noOfFloorPlans | Count of distinct floor plans in the unit mix table, or distinct unit types in a rent roll when there is no unit mix table | Don't count from photos or site plans |
| Acres | acres | Site area in acres | Convert only if a source states land area in square feet and labels it as site area |
| Parking spaces | parkingSpaces | Total parking spaces | If only a ratio is given, multiply it by the unit count and round to a whole number. Say in the source that it was derived (for example "OM p. 6, 1.5 per unit x 312 units") |
| Year renovated | yearRenovated | Year the most recent renovation was completed | Range of years: use the last. Ongoing or planned renovation: leave blank |
| Building type | buildingType | The Radix option closest to how the source describes the buildings | It doesn't need to match the wording; pick the nearest option (for example "three-story walk-up" as Garden). Leave blank only if no source describes the buildings |
| Asset class | assetClass | The property type (conventional, student, senior, affordable, etc.) | Set only when a source is explicit. Mixed or unclear: leave blank |
| Age restricted | ageRestricted | true for 55+ or 62+ communities | |
| Affordability program, Affordable unit share | affordability, affordabilityRate | Program (LIHTC, Section 8 HAP, inclusionary, etc.) and the percent of restricted units | Exactly as stated. Never from the web |
| University | universityAffiliation | The university a student housing source names | Student housing only |
| Start of operations | startOfOperations | First move-in date for new construction or lease-up | |
| Asking price | askingPrice | The stated asking price or price guidance | "Unpriced" or "call for offers": leave blank. If it is guidance, say so in the source |
| Cap rate | capRate | The in-place or trailing cap rate the OM states at the asking price | Never a pro forma or year-one cap rate. Never calculated |
| Trailing NOI | trailingNoi | NOI the OM labels as trailing actuals (T12 or a stated trailing period) | Not "adjusted", not pro forma, not year one, and not taken from an uploaded T12. If only an adjusted figure is shown, leave blank and mention it |
| Bid due date | bidDueDate | Call-for-offers date | From the OM or a broker email only |
| Seller, Current owner | seller, currentOwner | Owner as named in the sources | Many OMs withhold the seller. Leave blank rather than search |
| Last sale date, Last sale price | lastSaleDate, lastSalePrice | Prior sale, only if a source states it | |
| Parcel number | parcel | Parcel number (APN) as printed | Several parcels: list them all, comma separated |

## Sources first, then web

Search only when the web setting is on and the user's sources don't have the value. Record the exact URL for each web value. If a web value disagrees with the user's sources, keep the source value and mention the difference.

| Report as | API field | What to enter | Acceptable web sources |
|---|---|---|---|
| Property website | propertyWebsite | The property's own leasing website | A site whose pages show the property's name and the same street address. Not listing sites (Apartments.com, Zillow and similar); use those only to find the link to the property's own site |
| Property manager | propertyManager | The current management company | The property website (often "professionally managed by" in the footer) or the management company's own site listing the property |
| Broker | broker | Listing brokerage, with the lead agent in parentheses, e.g. "CBRE (Jane Smith)" | The brokerage firm's own listing page or agent page |
| Broker email, Broker phone | brokerEmail, brokerPhone | Lead agent's email and phone | The brokerage firm's own agent page. Never guess an email from a naming pattern |
| Asset quality | assetQuality | The property's class as a letter grade (A, B, C, D) | The broker's listing page or another listing of this property that states its class. Don't grade it yourself from photos or rents |
| Amenities | pool, fitnessCenter, roofDeck, elevator, doorman, waterfront | true when the source lists the amenity | The property's own website amenities page only. Don't infer an elevator from building type or waterfront from a map |
| Year built | yearBuilt | Year construction was completed | The county assessor's property record or the property's own website. Phased properties: use the first phase and mention the phases in the report |

## Leave for the user

Never fill these from any source. Set them only when the user tells you the value.

- dealStatus (Radix sets the default), assignedTo, fund, buyer, dealType
- bidPrice, bidDate, expectedPurchasePrice, underwrittenPurchasePrice
- goingInCapRate, leveragedIrr, unleveredIrr, equityMultiple, requiredEquity
- dueDiligenceDate, saleDate, salePrice
- locationQuality
- comments (never written by this skill, even if the user's documents include notes)

## Resolving conflicts

- **Within one document:** prefer the property details table over narrative text, and a specific figure over a rounded one ("312 units" over "300+ units"). If two tables still disagree, use the property details table and mention the other figure in the report.
- **Several sources:** prefer marketing documents over a website, and the most recent document over older ones. A broker email with an updated bid date beats the OM.
- **Marketing sources against a rent roll:** the marketing figure wins for the unit count. Rent roll figures stay with the rent roll after upload.
- **User's sources against the web:** the user's sources win. Mention the difference, since it may mean the web page is out of date or management has changed.

## Value formats

- Money: a plain number in dollars, no symbols or commas (45000000)
- Percents: the percent as a number, so 5.25 means 5.25%
- Dates: YYYY-MM-DD
- Years: four digits
- Amenity flags: true or false
- Text: as written in the source, trimmed

In the report, show values the way a person reads them: $45,000,000, 5.25%, Mar 3, 2027, Yes.
