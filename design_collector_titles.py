"""Story-led title decisions within the existing design workflow."""

_TITLE_GUIDANCE = """**STORY-LED COLLECTOR TITLES**

Choose the headline alongside the hero photograph. Decide what this edition means to supporters and why they would display it years from now. Find language specific to that memory, achievement, relationship or club. Verify commentary, nicknames, tributes and historical references. Never invent a commentary line, fan chant or nickname. Use original editorial wording without attributing it as a quote. Honour explicit user locks on approved titles and artwork.

{selection}

Record the chosen title and one sentence explaining its connection to the photograph and supporters in REVIEW NOTES. Refine once within research if needed. {recheck}, recheck the title and placement against the story, refining typography within the authorised scope.

"""

_EXISTING_SELECTION = "Compare four to six short candidates from distinct emotional angles, including any title suggested in the brief. Judge supporter recognition, emotional truth, specificity, fit with the photograph and readability on a wall or as a thumbnail. Reject generic slogans and play-by-play descriptions. Use the athlete’s name alone only when that is a deliberate creative choice."

_NEW_SELECTION = """Compare a few concise candidates, including the brief's suggested title. For each, identify the visible photographic detail or verified story that earns its wording. Reject assumed feelings, invented relationships with a city, generic slogans and phrases that fit another athlete after swapping the place name. A jersey or transfer alone does not establish that a city became home.

Keep numbers out of headlines, including jersey/car numbers, scores, statistics and dates. Preserve authentic photographic numbers and the official edition badge. Keep factual supporting context separate from the headline.

Replace the brief's suggested title only when the alternative expresses a more precise, supported memory. Keep a strong suggested title or use a restrained subject-led title, including the athlete's name, when the photograph carries the emotion. Honour approved title locks. Fit wording, line breaks, hero movement and plaque into one readable composition; do not invent a stronger emotional claim to fill space."""


COLLECTOR_TITLE_GUIDANCE = _TITLE_GUIDANCE.format(selection=_EXISTING_SELECTION, recheck="Before the first save and during the existing second-pass review")
NEW_DESIGN_TITLE_GUIDANCE = _TITLE_GUIDANCE.format(selection=_NEW_SELECTION, recheck="Before generation and during final inspection")
