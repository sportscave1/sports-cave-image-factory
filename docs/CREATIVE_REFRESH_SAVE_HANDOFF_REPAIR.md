# Creative Refresh save and Posting handoff repair

Local verification: 9 October 2026. No live provider writes were used.

## Cause

`ads_refresh_ui.execution_review` asked users to paste execution JSON. The
`creative_refresh_quality_issues` result then gated Save, POST NOW, the save
backend and Instant Experience package readiness. Empty execution records,
unperformed visual reviews and missing source-mapped copy reviews therefore
blocked otherwise useful advertising work. A second guard required every image
before a refresh could be saved. The saved-package/Posting path also assumed
five Carousel cards, although Creative Refresh retained the source winner's
card count.

## Repair

- Removed the execution JSON editor and technical review gates. Existing review
  data remains in the workspace; nothing marks unperformed reviews as passed.
  Previously supplied image prompts remain available in a collapsed viewer.
- Reused the existing Dropbox `creative-refresh-workspace.json` persistence and
  integrity checks. Incomplete copy and actual available media can be saved as a
  draft. Full export paths still use their existing files and CSV formats.
- POST NOW loads the saved snapshot into Posting; it does not call Meta. No CSV
  reupload is needed. Product association, source winner provenance, all authored
  copy, card order, media bytes and original filename references stay in the
  saved workspace. Existing export filename rules remain in effect.
- Missing media remains missing. Sparse image positions are hydrated by position,
  so a missing second image cannot move image three into its slot.
- Saved refresh Carousels retain 2–10 ordered cards, including four-card winners.
  Manual Carousel CSV imports still require five rows; five ad-level primary
  text variations and all existing Meta creative settings remain unchanged.
  The posting engine's count validation/payload/readback uses the explicitly
  supplied saved count. PAUSED status and existing recovery/idempotency remain.
- Posting retains real image, copy, destination, account and targeting checks.
  Conflicting per-card destinations are preserved and block Create Ad with an
  explanation; the existing Posting engine supports one product destination.
- A failed durable workspace write leaves entered work intact and disables the
  handoff. A later successful save re-enables it. A new save invalidates the old
  package first, including when a formerly complete IE becomes incomplete.
- Standard single-image refreshes can save incomplete drafts into their existing
  review-only Posting route. This does not add single-image Meta publishing.

## Files

Application changes:

- `ads_page.py`: optional-review gates, draft save, durable snapshot/handoff state.
- `ads_refresh_ui.py`: removed technical JSON editing requirements.
- `ads_refresh_draft.py`: incomplete workspace-to-Posting package adapter.
- `ads_posting_handoff.py`: validates incomplete saved refresh packages and mapping.
- `ads_posting_page.py`: actual card count, sparse media hydration, draft messaging.
- `ads_standard_workflow.py`: allow incomplete Creative Refresh draft saving.
- `meta_posting_service.py`: explicit Carousel count; existing defaults retained.

Tests and local fixture tooling:

- `tests/test_ads_refresh_draft.py`
- `tests/test_ads_refresh_draft_ui.cjs`
- `tests/test_ads_carousel_evolution.py`
- `tests/test_ads_posting_handoff.py`
- `tests/test_ads_refresh_repair.py`
- `tests/test_ads_refresh_save_restore.py`
- `tests/fixtures/refresh_ui.py`
- `scripts/run_refresh_save_tests.py`
- `scripts/run_refresh_browser.py`

## Verification

387 focused tests passed (29.862 seconds). Covered optional/empty/unperformed
review metadata; Greg Murphy four-card fixtures; incomplete and complete saves;
failed workspace persistence and retry; stale-package replacement; sparse image
mapping; saved workspace reopening; CSV compatibility; IE and standard-ad draft
handoff; Meta Review Carousel contract; and mocked Meta creation/recovery.

The four-card mock retry test confirms one campaign, one ad set, four image
uploads, one creative and one confirmed PAUSED ad after a simulated first-ad
failure. This verifies the existing duplicate safeguards in the tested path;
it is not a claim that every possible external failure is automatically safe.

Browser tests use a real local Streamlit renderer with fake Dropbox, product
metadata and blocked external requests:

- Four-card draft: edit headline, Save, POST NOW into the real Posting renderer,
  disabled Create Ad for missing media, Refresh Meta rerender, and return with
  edited copy retained; checked at 1440px and 390px.
- Existing IE and five-card Carousel: prompt clipboard, image upload/preview,
  Carousel CSV import, save and handoff; checked at 1366/1024/750/390px. No
  horizontal overflow or Streamlit exception was observed.

Local mocked timing sample: IE initial render 2.141s and save 1.261s; Carousel
initial render 1.658s and save 1.853s. These include browser/test overhead and
mocked storage. They are not production latency measurements or evidence of a
before/after production speedup.

The broader legacy `test_ads_page` checks have four failures concerning an old
prompt source string, optional sections, URL-parameter heading and code-widget
count. All four also fail with `ads_page.py` from pre-repair commit `271bd14`.
They were not weakened to make this repair appear green.

## Release caveats

No live ads, campaigns, provider emails or Dropbox writes were created during
these tests. No deployment or Git write was performed by this repair session.

While work was in progress, another actor's commit `87b0ea5` captured intermediate
edits under an Email Performance V5 title. The final corrections and tests remain
local. That intermediate commit alone is not this verified repair. Its deployment
status was not checked; review all final local changes before any release.

No database migration, infrastructure or permission change is required. Existing
single-image Posting remains review-only. Final Meta configuration/media checks
still apply, and live provider behavior has not been exercised.
