# True Winner Carousel copy evolution V2

Implemented locally on 9 October 2026 against `d57eec7`. No commit, push,
deployment, Meta/Shopify publication or provider writes were performed.

## Cause found in the active pipeline

The active route is `ads_page.build_ads_result_record` → `build_ads_prompt` →
`ads_refresh_generation.build_prompt` → `build_carousel_refresh_prompt`.
Changes are in this route, not the older inactive prompt builders or a one-off CSV.

Three code-level conflicts explained the drift risk:

1. The Carousel prompt requested a **new hook, argument and expression**, with no
   source-relative word or sentence bounds. It did not bind five outputs to five
   particular original primary texts.
2. It imported New Ads card rules that prioritised race/circuit/history over fan
   identity and collector ownership, and discouraged room language. That could
   replace a framing/gallery or man-cave card's actual selling role.
3. The generic duplication gate compared each refresh to the entire original copy
   pool using similarity thresholds, encouraging unnecessary distance from the winner.

These are verified prompt/validation defects; they do not establish which internal
model decision produced a particular historical advertisement. No model execution
logs or variation-level sales attribution were available or inferred.

## Implementation and mapping

`SPORTS_CAVE_CAROUSEL_WINNER_COPY_EVOLUTION_V2` is now the high-priority contract
for new Carousel Refresh plans. Other formats retain their existing contracts.

The prompt includes a catalog of actual source text, stable source IDs, word and
character counts, sentence/fragment counts, non-empty line counts, paragraph
counts and allowed word ranges. `PRIMARY_1` is an original shared variation,
not Card 1. `CARD_2_HEADLINE` refers only to Card 2's actual headline.

Five primary outputs must map to five distinct originals when available. With
more than five originals, the reviewer selects five relevant distinct angles and
records reasons, without claiming performance evidence for an individual variation.
With fewer than five, every available original is covered and any reuse is explicitly
recorded. Exact duplicate source text is deduplicated while retaining source IDs.
Missing or malformed source copy is an explicit blocking problem, never an invented baseline.

Primary word ranges use ±15% rounded down to whole words, with at least two words
of tolerance: 20→17–23, 40→34–46, 60→51–69. The gate checks sentence/fragment and
non-empty line counts within one, plus the same paragraph count. Card fields use
±1 word and the existing 17-character ceiling, with no commas/full stops or line
breaks. Shared original headlines/descriptions have independent relative bounds;
they do not inherit the card character ceiling. If those originals are unavailable,
concise derived options explicitly say `derived_no_original` and identify their
actual source basis. No fabricated original headline/description is recorded.

Meta Review now retains available asset-feed headline/description options, including
the static shared option when distinct, through its existing normalized handoff.
This reads data already retrieved; it introduces no extra API requests.

The existing execution-notes JSON array holds per-card `copy_review` and
`visual_review`, with `shared_copy_review` on its first record. Each copy review
binds exact source text and final output text, source ID, output position, selection
reason, source analysis and evidence for six qualitative checks: strategy, emotion,
style, meaningful improvement, verified facts and natural complete words.
There are no new controls or CSV columns.

The backend Save/Post gate rejects missing mappings, stale reviews after copy/source
edits, length/structure drift, changed numeric facts, unsupported stock claims,
generic additions, incorrect card order and an incorrect selected product URL.
Failed checks identify the individual field to revise. Uploaded images and entered
copy remain available. Existing notes persistence and content signatures cover the
new review data. Historical packages without the new copy marker keep their old
validation; regenerating their prompt opts into the new contract without discarding
manual output.

Qualitative declarations are not automatic semantic verification. A reviewer must
judge whether the wording truly preserves the source strategy and improves clarity.
The program does not claim that a similarity score establishes this.

## Greg Murphy proposed copy, reviewed example

These are proposed refinements of the user-supplied originals, not published ads or
performance-tested winners. Counts include spaces and punctuation.

| Card | Original headline (characters) | Proposed headline (characters) | Original description (characters) | Proposed description (characters) |
|---|---|---|---|---|
| 1 | Lap Of The Gods (15) | Lap Of The Gods (15) | Limited Edition (15) | Collector Edition (17) |
| 2 | Gallery Framed (14) | Gallery Presence (16) | Collector Piece (15) | Framed For Pride (16) |
| 3 | True Fans Only (14) | For The Faithful (16) | Man Cave Ready (14) | Your Cave Awaits (16) |
| 4 | Limited To 100 (14) | 100 Editions Only (17) | Collector Series (16) | Exclusive Series (16) |

Card 1 retains the protected product identity; its description changes. Card 2
stays about gallery presentation and framing. Card 3 keeps fan belonging and the
personal sports space. Card 4 retains the edition limit of 100, with no claim about
remaining inventory. All card fields stay within one word of their originals.

Original — **27 words**, four non-empty lines, two paragraphs, five sentences/fragments:

```text
Some laps become folklore.
This one became Bathurst scripture.
A tribute to the day Murph bent the mountain to his will.

Limited 100 run. Don't miss it.
```

Proposed — **26 words**, the same line/paragraph/sentence pattern:

```text
Some laps never leave you.
This one still echoes through Bathurst.
Remember the day Murph made the mountain his own.

Just 100 editions. Make one yours.
```

The hook shifts to personal recall, the Bathurst line keeps a dramatic sporting
metaphor, and the close retains scarcity plus an ownership CTA. It does not become
a historical explanation. The fixture's other four primary originals are explicitly
synthetic angle-coverage data, not claimed real Greg Murphy winners.

## Visual continuity

The existing collective product authority and each card's own creative authority
remain intact. Every standalone prompt lists all four references, locks the complete
artwork/frame, preserves its own source role/family and requests 1080×1080 output.

The Carousel brief now explicitly reinforces gallery/entrance continuity,
functional home-bar continuity, and edition-detail/magnification using the existing
badge without changing numbers. New architecture/layout/materials, lighting,
placement and photographic composition remain required; a recolour or slight
angle change is insufficient. Vehicles, sponsors, signatures and printed details
remain immutable. Source-preserving compositing is preferred.

No actual winner pixels or newly generated image batch were assessed in this task.
Tests use synthetic image fixtures and declared analyses. Final images still need
visual inspection; no pixel-fidelity or sales-performance guarantee is made.

## CSV and Posting compatibility

The existing CSV schema, headers, row identities, CTA, five populated primary,
headline and description variations, four ordered card pairs, image slots and
verified destination URL remain intact. Query parameters and fragments survive
the CSV roundtrip. Analysis stays outside production CSV. Mocked Save/reopen and
the existing five-card Posting handoff pass with the new notes preserved.

**Existing limitation:** `POST NOW` supports five-card Carousel packages. The Greg
four-card refresh saves/exports all four cards but remains blocked from that
five-card-only handoff. No fifth card is added or card dropped. The posting engine
was not expanded or changed by this prompt-quality task.

## Validation

- Initial unchanged-source check: 73 tests passed; one AppTest was blocked by the
  Windows sandbox temporary-directory permission. Subsequent local runs used the
  normal temporary directory and mocked providers.
- New evolution suite: **35 tests passed**, including the actual UI review failure
  and recovery, four-card save/export, metadata handoff, relative lengths, missing
  sources, stale mappings, partial source pools, card roles, CSV and source URLs.
- Final focused suite: **327 tests, 326 passed, one pre-existing failure**, 25.240s.
- The single failure,
  `test_ie_refresh_all_three_briefs_include_premium_fomo_rules`, expects three
  unsplit IE rules blocks. It also fails **0 != 3 against unchanged HEAD source**
  loaded in memory. No test was weakened or skipped to hide it.
- All **25 captured non-Carousel-Refresh prompts** remain byte-identical: New Ads
  formats, Instant Experience Refresh and Single Image Refresh.
- Python compilation and `git diff --check` passed. Tests used mocked storage,
  Meta fixtures and offline Streamlit fixtures. No live ads or provider writes.

Final focused command:

```text
.venv\Scripts\python.exe -m unittest tests.test_ads_carousel_evolution tests.test_ads_refresh_generation tests.test_ads_refresh_plan tests.test_ads_refresh_repair tests.test_ads_refresh_save_restore tests.test_meta_review_creative tests.test_ads_posting_handoff tests.test_posting_import_csv tests.test_ads_refresh_workflow tests.test_ads_ie_refresh_realism_priority tests.test_ads_winner_refinement tests.test_meta_review_products tests.test_ads_refresh_reference tests.test_meta_review_carousel_contract tests.test_meta_review_live
```

## Files changed

| File | Purpose |
|---|---|
| `ads_carousel_evolution.py` | New source catalog, high-priority instructions, source-relative copy/review validation |
| `ads_refresh_generation.py` | Wire the contract into the active Carousel builder; remove conflicting strategy rules |
| `ads_refresh_plan.py` | Version new Carousel copy plans; reinforce same-family visual execution |
| `ads_page.py` | Prompt version and existing Save/Post quality-gate integration |
| `meta_review_creative.py` | Preserve actual shared headline/description originals in Carousel handoffs |
| `tests/test_ads_carousel_evolution.py` | 35 focused regression tests |
| `tests/fixtures/carousel_evolution.py` | Greg example and explicitly synthetic review fixtures |
| `tests/test_ads_refresh_plan.py` | Give existing Carousel tests explicit synthetic source copy/review mappings |
| `tests/fixtures/refresh_ui.py` | Keep existing UI/save fixtures valid under the new copy contract |
| `docs/CAROUSEL_WINNER_COPY_EVOLUTION_V2.md` | This delivery report |
