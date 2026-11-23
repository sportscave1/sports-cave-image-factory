"""Prompt wording only; no validation gates, storage or execution changes."""
from functools import wraps
from inspect import signature
from ads_ie_scenes import NEUTRAL_WALL_RULES

CONTINUITY = """SPORTS CAVE AD PROMPT LANGUAGE — CONTINUE WITH SUPPORTED CONTENT
Treat supplied product references as edition identity and visual evidence. Write truthful collector advertising using the supplied facts and established owner-confirmed edition policies. For uncertain optional claims about achievements, endorsement, affiliation, licensing, autographs, stock or offers, omit the claim and use grounded emotional collector wording in the same field. Do not turn an optional copy uncertainty into a campaign-wide refusal, approval request or workflow stop. An edition name or depicted sporting subject alone does not establish endorsement or affiliation; do not claim either without evidence.
Continue all independent requested ads, copy, CSV and setup using available valid inputs. Request only an essential missing input when that specific output cannot be completed accurately. Keep the existing image calls, review, retries, output count and CSV schema. Respect actual provider safeguards and errors, retain completed work and report unavailable outputs honestly; never bypass a provider refusal or promise ad-platform approval.
"""

AU_COPY = """AUSTRALIAN INSTANT EXPERIENCE — STRICT NAME-FREE CUSTOMER COPY V1
For Australia / AU Instant Experience only, write emotional, nostalgic and collector-led copy. No athlete, player, driver, coach, team or club names in any customer-facing Title, written Meta Headline, Description or Primary Text, including the post's opening/title line and displayed AD COPY and matching CSV copy cells. Do not use first names, surnames, initials, abbreviations or team names as substitutes.
Refer to the edition by its supplied edition name only after excluding any athlete/team name within that name. Never paste the full product title into customer copy when it contains a name. If no separate name-free edition name is supplied, use 'this edition' and grounded fan/collector emotion; do not invent a new edition title.
A nickname is optional: use it only when confidently known as an established, widely recognised nickname for this exact subject in this sport. GOAT, The King and similar terms are examples of possible established nicknames, never automatic labels or a nickname bank. Never guess, invent or assign a nickname merely because it suits the copy. If uncertain, omit the nickname and complete a nostalgic collector post without one; no research/confirmation gate.
Use supplied sporting meaning, era and supporter connection without invented memories, achievements or events. Personalise the flexible lines of the existing description frameworks through that emotion and the name-free edition reference. Supplied athlete/team metadata and winning ads identify the subject internally; they are not wording to repeat in these fields. This rule replaces any instruction to name the athlete/team or preserve a name in newly generated customer copy, including copy optimisation and refresh.
Keep the assigned name-free on-image headline, supporting/FOMO line, footer split, Meta headline assignment and CTAs verbatim. Do not add subject names to any new headline or footer. Preserve names already printed inside the immutable original edition, internal product identity, filenames, URLs, route IDs and non-copy CSV cells. Keep all copy frameworks, short lines, blank lines, approved scarcity, image workflow and export behaviour. In the existing internal copy review, remove any subject names from flexible customer copy and reuse the same final wording in display and CSV; no new review or blocking step.
"""


def australian_ie(country, campaign_type):
    return str(country or '').strip().casefold() in {'australia', 'au'} and campaign_type == 'Instant Experience'


def apply(prompt, country='', campaign_type=''):
    if not prompt:
        return prompt
    rules = '' if CONTINUITY in prompt else CONTINUITY
    if NEUTRAL_WALL_RULES not in prompt:
        rules += '\n' + NEUTRAL_WALL_RULES
    if australian_ie(country, campaign_type) and AU_COPY not in prompt:
        rules += '\n' + AU_COPY
    if not rules:
        return prompt
    # Keep version markers first and CSV templates last, byte-for-byte.
    header, separator, body = prompt.partition('\n')
    return header + (separator or '\n') + rules + '\n' + body


def prompt_language(builder):
    params = signature(builder)
    @wraps(builder)
    def wrapped(*args, **kwargs):
        bound = params.bind(*args, **kwargs)
        values = bound.arguments
        return apply(builder(*args, **kwargs), values.get('country', ''), values.get('campaign_type', ''))
    return wrapped
