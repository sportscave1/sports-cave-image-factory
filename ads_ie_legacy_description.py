"""Description style rules recovered from ads_page.py at 844a0c5.

Historical numbered option headings are unnumbered here: styles are an internal
library, not additional output rows. No historical fallback claims are generated.
"""

VERSION = "WINNER REFINEMENT LEGACY DESCRIPTION STYLE V1"

HISTORICAL_STYLES = """Legacy Standard:
- Four short opening lines establishing the safe relationship or product meaning.
- Blank line.
- "This isn't wall art."
- One short representation line.
- Blank line.
- Verified scarcity in two short lines.
- Blank line.
- "Secure yours."
- Do not use "They didn't compete" for real rivals.
- Use singular language for a single athlete. Use female pronouns only when verified.

Framed Greatness:
- One short greatness/framed hook.
- Blank line.
- Two collector-identity lines.
- Blank line.
- Three short scarcity lines.
- Blank line.
- "Secure yours."
- Prefer "Greatness doesn't fade. It gets framed." unless a rivalry, historic moment or motorsport hook is more product-accurate.

Choose a Side:
- A short question or fan-identity challenge.
- Blank line.
- One sharp response.
- Blank line.
- A second athlete, team, moment or identity question.
- Blank line.
- A line showing the fan already knows their answer.
- Blank line.
- Verified scarcity.
- Blank line.
- A two-line ownership challenge.
- Use rivalry framing only when ARTWORK_TYPE or RELATIONSHIP_TYPE verifies rivalry/opposition.
"""


def build_description_style_rules():
    return f"""{VERSION}
RESTORED SPORTS CAVE INSTANT EXPERIENCE DESCRIPTION STYLE
Choose the historical framework that best fits the winning ad and verified product. Use it for one finished description per ad. The three ads remain close siblings: do not force a different framework or emotional proposition onto each sibling. Keep the winner's hook and meaning; restore concise Sports Cave wording, not explanatory marketing prose.

{HISTORICAL_STYLES}

HISTORICAL CHOOSE-A-SIDE ADAPTATION
This was not a generic third slogan. For verified rivalry/opposition use the supplied sides, a question, "No middle ground.", "You already picked a side.", verified scarcity and "Choose it…\nor watch it end up on someone else's wall."
For a single athlete, use the supplied subject: "You know the name."; use "You remember." only with a supported moment, then "No explanation needed." and the historical "Claim it…\nor watch it end up on someone else's wall." close.
For verified connected legends the original contrast was "Wrong question." rather than invented rivalry. Team, historic-moment and motorsport variants must follow verified product context. Never invent a relationship, mountain, race, viewer memory or nostalgia merely to reproduce an old example. Choose another historical framework if this one does not fit the winner.

APPLICATION TO THE EXISTING SINGLE-COPY CONTRACT
Return only the selected finished wording. Never print these three templates as three options under one ad. Each ad has exactly one primary text, one headline and one Instant Experience description: Primary Text / Description is the existing shared copy field, stored once in primary_text, not two alternative versions or a new CSV column. Exactly three complete ad combinations total.
Use short, strong, collector-led lines and intentional blank lines; approximately 35–65 words only when useful, never pad. Preserve "This isn't wall art.", "Greatness doesn't fade. It gets framed." and "Secure yours." where the selected historical framework calls for them. No generic ecommerce explanation, bloated sentences or AI luxury language. The description's closing words do not replace the existing CTA field.
Keep current factual safeguards: supplied identity only, rivalry only when verified, exact verified edition limit, no invented remaining stock, no reprint, no second run or retirement. Never append worldwide or world wide to scarcity. Do not change the winning urgency, scarcity style, headline count, image briefs, CSV identities or output row count.
"""
