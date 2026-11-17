"""Story-led title decisions within the existing design workflow."""

_TITLE_GUIDANCE = """**STORY-LED COLLECTOR TITLES**

Choose the headline alongside the hero photograph. Decide what this edition means to supporters and why they would display it years from now. Find language specific to that memory, achievement, relationship or club. Verify commentary, nicknames, tributes and historical references. Never invent a commentary line, fan chant or nickname. Use original editorial wording without attributing it as a quote. Honour explicit user locks on approved titles and artwork.

{selection}

Record the chosen title and one sentence explaining its connection to the photograph and supporters in REVIEW NOTES. Refine once within research if needed. {recheck}, recheck the title and placement against the story, refining typography within the authorised scope.

"""

_EXISTING_SELECTION = "Compare four to six short candidates from distinct emotional angles, including any title suggested in the brief. Judge supporter recognition, emotional truth, specificity, fit with the photograph and readability on a wall or as a thumbnail. Reject generic slogans and play-by-play descriptions. Use the athlete’s name alone only when that is a deliberate creative choice."

_NEW_SELECTION = """From the verified brief, complete: “A supporter would keep this on their wall because they remember ___.” Develop four to six concise titles expressing different emotional angles, including the brief’s suggested title.

Choose emotional meaning the photograph and name cannot already convey. Keep numbers out of headlines, including jersey/car numbers, scores, statistics, dates and spelled-out numbers. Reject interchangeable city-and-number labels, generic slogans and play-by-play descriptions. Preserve authentic photographic numbers and the official edition badge.

Compare the winner directly with the brief’s suggested title; replace it only for a more precise supporter memory. Story specificity and emotional truth decide; readability settles close choices. Honour approved title locks and preserve the chosen meaning through layout."""

COLLECTOR_TITLE_GUIDANCE = _TITLE_GUIDANCE.format(selection=_EXISTING_SELECTION, recheck="Before the first save and during the existing second-pass review")
NEW_DESIGN_TITLE_GUIDANCE = _TITLE_GUIDANCE.format(selection=_NEW_SELECTION, recheck="Before generation and during final inspection")
