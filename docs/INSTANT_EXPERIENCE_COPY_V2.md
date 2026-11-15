# Instant Experience Copy V2

Implemented locally on 16 September 2026. No commit, push, deployment, posting or live Meta changes.

## Architecture and active path

The previous workflow required three archetype rows for each of three covers.
This was enforced by the base master prompt, later output/text-first contracts,
the copy field renderer, completeness checks, CSV writer and package text exports.

New Ads Submit still calls `build_ads_result_record` → `build_ads_prompt` →
`build_standard_instant_experience_prompt` → `compose_final_ads_prompt`.
The Copy V2 version invalidates cached older prompts. The existing three-format
visual wiring and stale-cache checks remain active.

Each visual now has one visible **Ad Copy** section: Description, Headline, CTA.
Statuses say Copy complete or Copy needed. Visible names and defaults are:

| Visual | Supporting label | Copy job | Default CTA |
| --- | --- | --- | --- |
| Premium Scarcity — Smart Hybrid | Product-aware scarcity hero | Product meaning, conversion and truthful urgency | Claim Your Edition |
| Private Gallery | For the room that remembers | Memory, legacy and collector prestige | Secure Your Edition |
| The Cave | Premium fan sanctuary | Identity, belonging and ownership | Own This Edition |

All three CTAs remain in the approved family. Imported approved CTAs are preserved.
The native Meta button stays Shop Now. URL parameters and catalogue setup stay unchanged.

## Copy selection

`ads_ie_copy.py` holds internal writing families and deterministic route cues.
Legacy Standard, Framed Greatness and other successful patterns remain available
internally. Choose-a-Side is allowed only for verified rivalry/opposition.

The prompt requires reading title, artwork wording and metadata; empty structured
athlete fields do not erase an explicitly named title subject. It forbids facial
identification, inferred teams, fabricated events and extrapolated claims.
Optional research is capped at 2–4 searches, with official/reputable sources,
and informs emotional context rather than automatically adding customer-facing
facts. No research report, citations in ad fields, candidates or scores are returned.

USA defaults to identity/belonging; Australia defaults to supported historical
memory. Product truth overrides both. Current Australian subjects must not be
forced into nostalgia. Other markets keep existing localisation.

SHA-256 of token, visual family, product and market selects hook, rhythm,
headline family and scarcity-close cues. Recent same-market/sport hooks are
avoided when suitable. The existing session fingerprint history now also records
selected cues and completed copy's normalized opening sentence and headline.
No database was created and no existing published ad is rewritten.

Descriptions normally target 35–65 words and a meaningful product anchor;
headlines normally use 4–6 words, with six as the maximum. Numeric scarcity
requires verified data. Neither copy nor image edition claims append worldwide.

## Compatibility

New CSVs contain **three rows**, with the same columns and schema version.
`output_mode=three_visual_copy_v2` distinguishes them from legacy nine-row files
and Creative Refresh. Machine route keys, variation 1 and its historical
description metadata remain stable transport identifiers, not visible choices.

Legacy nine-row CSVs are fully validated and preserved in
`legacy_instant_experience_copy`; the first ordered row per route becomes active.
New exports contain those three active rows without triplicating content.
Invalid imports fail before changing workflow state. Existing legacy modes and
Creative Refresh imports remain supported.

Posting's shared CSV adapter recognizes the new mode and hydrates three ads,
each with one variation. Historical nine-row Posting behavior remains covered.
Posting UI, publishing, URLs and catalogue behavior were not redesigned.

## Visual preservation

Captured pre-edit image hashes verify USA and Australia image prompt bytes.
Only two obsolete Meta-copy CTA instructions within Smart Hybrid were replaced
to consume the selected per-visual copy contract. Layout, footer, signatures,
room resolution, camera, artwork lock, lighting, shadows, frame/glass and quality
instructions are unchanged. Gallery and The Cave image bytes are unchanged.

## Files changed

- `ads_ie_copy.py` — new copy library and instruction builder.
- `ads_page.py` — active prompt contract, one-copy UI/state/export, compatibility and history.
- `posting_import_csv.py` — shared three-row mode adapter, preserving legacy paths.
- `tests/test_ads_ie_copy_v2.py` — seven new copy/integration tests.
- `tests/test_ads_ie_prompt_integration.py` — actual Submit/clipboard contract updated.
- `tests/test_ads_ie_visual_systems.py` and `tests/test_ads_instant_experience_footer.py` — new copy contract alongside unchanged visuals.
- `tests/test_ads_page.py` — prompt/UI expectations; explicit historical CSV fixtures.
- `tests/test_posting_import_csv.py` — explicit nine-row compatibility fixtures.
- `tests/test_ads_image_workflow.py` — one-active-copy package export expectations.
- `tests/fixtures/ie_copy_v2_visual_baseline.json` — pre-edit visual hashes.
- `tests/fixtures/carousel_detail_prompt_baseline.json` and `tests/fixtures/carousel_winner_unaffected.json` — intentional New IE hashes only.
- `docs/INSTANT_EXPERIENCE_COPY_V2.md` — this report.

## Validation results

The combined copy, public prompt, real UI, visual, footer, CSV, Posting hydration,
image workflow, Creative Refresh, Carousel and shared prompt suite ran
**194 tests in 21.154s**. 193 test methods passed; the only failing method has
four pre-existing Creative Refresh captured-byte mismatches (Motorsport,
Football, Cricket, NBA). Those baselines were not rewritten.

Full Ads-page suite: **193 tests in 133.682s, 191 passed, 2 failed**. Remaining
failures are the existing dropdown-order expectation and an earlier Carousel
specificity sentence. All Instant Experience Ads-page tests passed.

An independent comparison against repository HEAD confirmed **25 unchanged
public prompts** across five sports: Carousel, Single Image and all Creative
Refresh campaign types. Python compilation and `git diff --check` passed.

New tests cover title anchors with empty structured identity, USA history,
Australian historical/current subjects, rivalry gating, unverified limits,
deterministic/fresh copy cues, actual Submit → UI → CSV → Posting hydration,
transactional imports, actual-copy history and exact visual preservation.

## Manual render review

Rendered two complete prompts using token `manual-copy-v2`:

| Supplied product | Market | Resolved hooks: Smart Hybrid / Gallery / Cave | Lens |
| --- | --- | --- | --- |
| Don Mattingly October 4 1995 | USA | legacy_standard / quiet_collector / ownership_belonging | identity_belonging |
| Peter Brock Historic Motorsport | Australia | legacy_standard / era_memory / collector_pride | supported_memory |

Each rendered prompt contains three grouped AD COPY blocks, all three correct
CTAs, the unchanged URL parameters and distinct visual jobs. These are prompt
renders: the application hands instructions to ChatGPT and does not run a copy
model locally. Final model prose quality remains subject to that generation;
the tests verify the actual instruction, editing and transfer paths.
