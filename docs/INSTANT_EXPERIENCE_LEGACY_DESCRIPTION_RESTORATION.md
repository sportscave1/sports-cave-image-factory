# Restored Creative Refresh Instant Experience description style

Local-only change. No commit, push, deployment or live Meta changes.

## Source and cause

`build_ads_prompt` returns `build_instant_experience_winner_refinement_prompt`
directly for Instant Experience with a winner context. That builder, introduced
in commit `3f429c5` (Repair Creative Refresh winner refinement workflow), retained
only generic small-improvement guidance and omitted the historical description
framework. New Ads Copy V2 is a separate path and is unchanged by this repair.

Git searches for both “Greatness doesn't fade” and “This isn't wall art” located
commit `844a0c5` (Upgrade Instant Experience prompts and description copy).
`ads_page.py` at that commit contains
`build_instant_experience_description_generation_prompt`,
`_legacy_standard_opening`, `_framed_greatness_hook`, `_choose_a_side_copy` and
`build_instant_experience_description_variants`.

The exact historical instruction blocks below were recovered with `git show`.
An explicit comparison confirms they are unchanged except that numbered
Description 1/2/3 headings are now unnumbered internal style names.

## Exact recovered templates

```text
Legacy Standard:
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

```

The historical third implementation was conditional, not a fixed slogan:
verified rivals used “No middle ground.” and “You already picked a side.”;
connected legends used “Wrong question.”; single athletes used “You know the
name.” or “You remember.” depending on a supplied moment. Team, historic-moment
and motorsport branches also existed. The original ownership close was
“Choose it…” for opponents or “Claim it…” otherwise, followed by
“or watch it end up on someone else's wall.”

The restoration preserves these behaviours under existing factual safeguards.
It does not blindly emit old example claims about a mountain, rivalry, event or
viewer's memory. The best suitable historical framework supports the winning
ad; the three siblings are not forced into three unrelated styles.

## Active output and unchanged behaviour

The shared style helper is inserted into the actual winner-refinement master
prompt, which is also the generated/exported prompt text. A scoped version bump
refreshes cached prompts without replacing completed user copy.

Exactly three ad combinations remain, one Primary Text / Description and one
Headline per ad, with the existing CTA and three-row winner_refinement CSV.
In the existing app, the Instant Experience Description and Primary Text refer
to the same stored `primary_text` copy field. No fourth copy field, extra option,
CSV column or second rendering of that copy has been introduced.

Winner selection, scoring, ROAS, hydration, Save → POST NOW → Posting, Meta API,
Meta Review, Supabase, image briefs and New Ads prompts were not changed.

## Files changed for this repair

- `ads_ie_legacy_description.py`: recovered templates and single-copy application rules.
- `ads_page.py`: one helper insertion in the active builder and scoped cache version.
- `tests/test_ads_ie_legacy_description.py`: three new public-entry/cache/scope tests.
- `tests/test_ads_winner_refinement.py`: explicitly mark the historical nine-row fixture as legacy.
- `docs/INSTANT_EXPERIENCE_LEGACY_DESCRIPTION_RESTORATION.md`: this report.

Other pre-existing uncommitted changes were preserved.

## Validation

- New description tests + Creative Refresh + saved-package/Posting handoff + CSV + Meta Review product tests: **144 passed in 13.490s**.
- Winner-refinement suite, including saved refresh → handoff → Posting: **16 passed in 0.161s**.
- Total: **160 tests passed**.
- Python compilation and `git diff --check`: passed.
- Historical template content compared directly with `git show 844a0c5:ads_page.py`: exact match apart from unnumbered headings.
