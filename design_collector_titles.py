"""Story-led title decisions within the existing design workflow."""

TIMELESS_ARTWORK_COPY_RULE = """No added scores, statistics, results, rounds, clock/finish times, dates or venue/event captions, including small print, even when verified or inherited. Use facts in research/metadata only. Preserve emotional titles, photographic numbers and edition numbering. Remove factual captions in full refreshes; targeted edits preserve unrelated locks."""

TIMELESS_ARTWORK_GUIDANCE = """**TIMELESS COLLECTOR ARTWORK — MANDATORY**

Create artwork supporters will want on their wall for years. Keep visible copy to the emotional title, necessary subject names and official edition badge. Do not add scores, match results, statistics, performance totals, record figures, rankings, rounds, periods, clock readings, elapsed/finish/split times, fixture dates or venue/result strips anywhere on the artwork. This includes subtitles, supporting captions, footers, plaques and small print, across every sport and both recent and historical editions. A fact being verified, essential to research or story-defining does not make it printable.

Use news, dates, results, times and statistics only to verify the story, photographs, era and sources, or in non-artwork research notes and metadata. A brief, source article, inherited caption or reference design is research context, never an instruction to print its factual details. Preserve the real venue through imagery rather than a match-report caption. These rules supersede older instructions to add verified supporting facts, a stat/date line or event context, or to preserve existing score/stat/time captions.

Preserve strong emotional titles such as The Right Hand, At the Buzzer and Two Golds. A number integral to verified fan language or a meaningful sporting phrase may remain in the title; this is not permission for a numerical recap. Preserve authentic jersey/car numbers, source-photo markings and the official edition numbering. Never fabricate or alter photographic evidence to remove a number, or enlarge incidental scoreboard information into a designed text feature.

For New Design and full Refresh, omit or remove standalone result/stat/time/event-caption text while preserving the title, subject, story and successful visual direction. Leave the freed space quiet or adjust nearby spacing; do not invent replacement copy or redesign the piece. For targeted Edit, never introduce this copy; when its removal is requested, change only that text and the nearby spacing needed to restore balance, respecting explicit locks on unrelated elements.

"""

TIMELESS_ARTWORK_CHECK = """Within the existing final inspection, read every visible word, including small supporting text. Confirm there is no added score, statistic, result, round, timing or fixture/event-caption line. Remove any that slipped through within the authorised scope, preserve the emotional title and successful composition, and recheck the saved render. Do not restore removed captions from references, inherited artwork or generation 1. No extra generation or review stage is required.

"""

_TITLE_GUIDANCE = """**STORY-LED COLLECTOR TITLES**

Choose the headline alongside the hero photograph. Decide what this edition means to supporters and why they would display it years from now. Find language specific to that memory, achievement, relationship or club. Verify commentary, nicknames, tributes and historical references. Never invent a commentary line, fan chant or nickname. Use original editorial wording without attributing it as a quote. Honour explicit user locks on approved titles and artwork.

{selection}

Record the chosen title and one sentence explaining its connection to the photograph and supporters in REVIEW NOTES. Refine once within research if needed. {recheck}, recheck the title and placement against the story, refining typography within the authorised scope.

"""

_EXISTING_SELECTION = "Compare four to six short candidates from distinct emotional angles, including any title suggested in the brief. Judge supporter recognition, emotional truth, specificity, fit with the photograph and readability on a wall or as a thumbnail. Reject generic slogans and play-by-play descriptions. Use the athlete’s name alone only when that is a deliberate creative choice."

_NEW_SELECTION = """Write from the supporter's point of view. Ask internally: What do fans actually call this athlete, and which verified nickname signals identity? What do supporters trust and opponents fear? Why does this club, rivalry or era matter? Could a nickname twist, double meaning or fierce word capture it? Would a fan proudly put these exact words on their wall?

Internally compare four distinct short candidates: established fan language, original wordplay joining two verified meanings, the athlete's defining quality, and a phrase drawn from the sporting action. For each, identify the visible photographic detail or verified story that earns its wording. Choose the strongest combination of fan recognition, emotional weight, natural phrasing and photographic fit. Read it aloud and imagine it framed with the athlete's name underneath. Seek memorable collector language rather than a match-report label. A familiar nickname can win; never force a pun. Let the emotion set the voice: fierce for rivalry, defiant for a comeback, affectionate for a cult hero, understated for a farewell. For a rivalry, use this same four-candidate comparison to choose the strongest short headline for the verified rivalry and the selected face-off or hard competition. Make the words feel specific to these opponents and their sporting tension; avoid a generic versus label, invented hostility or an unsupported result. Fit the winning title around both rivals while honouring approved wording locks.

Treat the brief's suggested title as one candidate unless explicitly locked. Replace interchangeable phrases such as New Chapter. Treat Statement, Greatness, Legacy and Chapter, or a place name carrying the whole idea, as signals to find a more specific emotional hook. Reject assumed feelings, invented relationships with a city and wording transferable to five other athletes. A transfer does not prove belonging. Verify nickname, team and era references and any implied result, record, farewell or decisive play; original wordplay is editorial, not an established nickname or quotation. Honour approved title locks.

Keep scores, statistics, rounds, dates and times in non-artwork research context only; never turn them into supporting copy. A number integral to verified fan language or a meaningful sporting phrase may remain when it earns the title. Preserve authentic photographic numbers and the official edition badge. Carry only the winning title into lettering and generation. Fit the winning words, hero and plaque into one composition. Complete this decision within the existing pre-generation review."""


COLLECTOR_TITLE_GUIDANCE = _TITLE_GUIDANCE.format(selection=_EXISTING_SELECTION, recheck="Before the first save and during the existing second-pass review")
NEW_DESIGN_TITLE_GUIDANCE = _TITLE_GUIDANCE.format(selection=_NEW_SELECTION, recheck="Before generation and during final inspection")

REFRESH_TITLE_GUIDANCE = """**PRESERVE THE EXISTING COLLECTOR TITLE AND STORY**

This refresh upgrades an existing edition. Read its current artwork and listing, then record the exact printed headline, any existing quotation and its attribution, the full product title and the sporting story or moment in REVIEW NOTES. Keep the edition name and headline wording, spelling and punctuation verbatim. Preserve the same subject, event, era, rivalry or career angle and emotional meaning. Research verifies that existing story and finds better authentic photographs to express it; it does not choose a different memory, newer achievement, alternative slogan or nickname.

Do not draft replacement titles or apply generic-title rejection to rename this edition. Even a headline that would not win a new-design title comparison remains the approved wording for this refresh. Preserved wording is not a locked layout. Improve its antique-gold lettering, scale, line breaks, placement and relationship to the new imagery, recognisable venue, abstraction and original plaque as one collector composition; never treat a name-only headline as permission for generic lettering or a detached badge. Preserve existing quoted wording and attribution; verify rather than invent or paraphrase it. Do not add a quotation to an edition that has none. Preserve story-defining facts in research notes and metadata, while removing existing standalone score, statistic, round, timing and fixture/event-caption lines under the timeless artwork rule. Preserving the edition story does not require printing a factual recap.

Choose hero, complementary action or opposing rivalry profiles, and venue references that serve the preserved story under the shared authenticity rules. Within the existing research and review checks, compare the locked words and story against the layout, generation request and assembled artwork. If source wording or a factual claim cannot be verified, record the specific uncertainty using the existing provisional and needs_attention handling; continue independent work and Review delivery without inventing wording, changing the story, adding an approval pause or generating again.

"""
