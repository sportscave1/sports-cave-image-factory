# Meta Review / Creative Refresh carousel UX

## Scope and preserved contracts

Presentation changes only. An AST comparison against the starting revision confirms the only changed functions in `meta_review_creative.py` are `render_cards` and `render_shared_primary_text`. Fetching, format resolution, ordered card normalization, hash mapping, metrics, automatic winner ranking, Posting, authentication and Meta mutations are unchanged. `meta_review_handoff.py` changes only the source display.

## Operator experience

- Campaign dialog caps at 1380px with viewport margins, tighter vertical gaps and smaller campaign headings. Ad rows are 48px instead of 64px; the table caps at 285px instead of 390px. The top summary keeps Spend, Sales, ROAS, CPA, CPC and Last Sale, beneath campaign name/status.
- Single selected row is the reference. It bypasses “Winner to use”; the automatic path remains when no row is selected. The selected preview appears once instead of both in details and the winner block.
- Apply is above the preview. The existing durable handoff/link behavior remains, with Open Creative Refresh alongside Apply after saving.
- One collapsed admin-only Diagnostics expander retains safe structural counts, source warnings and opt-in advanced winner tools. IDs, cache descriptions and source warnings are absent from the default VA preview.
- The shared browser component renders the full ordered card array at once. Meta Review cards are 160px; Refresh cards 190px. On small screens cards occupy 75% of the strip with horizontal scrolling and keyboard arrow support. Images use contain, preserving complete creative aspect ratio.
- Compact ordered card copy appears below, in two desktop columns; Primary Text is separate. Destination/CTA and delivery-order notes live under native Details.

## Image actions and performance

OPEN is a normal new-tab full-resolution link. COPY requests full resolution only on click, uses the image clipboard (PNG conversion when needed), and falls back to copying the URL. COPY IMAGE URLS copies one numbered URL per card in source order. Browser permission failures are reported locally; no Graph or Streamlit callback is involved.

Meta Review prefers already-resolved preview/thumbnail URLs. If no smaller URL exists it uses the supplied source, without guessing CDN transforms or changing normalization. Refresh preserves durable archived images after Meta URL expiry: it creates a maximum 440×440 JPEG preview once, caches media in the authenticated session (bounded to 20 entries), and serves full-resolution originals through Streamlit media storage only when requested. No base64 images in HTML. Four initial thumbnails load eagerly; later cards load lazily, all decode asynchronously. No new JS package or external asset.

Ad selection is a Streamlit fragment, so row selection reruns only the ad UI rather than campaign loading/aggregation. Image scrolling/open/copy runs entirely in the iframe, without Python reruns or Graph calls. Existing selected-creative cache and durable handoff are reused.

## Files

Production:
- `ads_meta_review_page.py`
- `meta_review_creative.py` (render functions only)
- `meta_review_handoff.py` (source display only)
- `meta_carousel_view.py`
- `components/meta_carousel_strip/index.html`

Tests/fixtures:
- `tests/test_meta_carousel_ux.py`
- `tests/test_meta_carousel_viewer.cjs`
- `tests/test_meta_carousel_modal.cjs`
- `tests/test_meta_review_carousel_contract.py`
- `tests/test_meta_review_creative.py`
- `tests/test_meta_carousel_detail.py`
- `tests/test_meta_review_live.py`
- `tests/test_meta_review_active_cpc.py`
- `tests/fixtures/meta_creative_cards_preview.py`
- `tests/fixtures/meta_carousel_campaign_preview.py`

## Verification

23 Python suites, 481 tests: 480 pass, one pre-existing error. The unchanged `test_ambiguous_asset_labels_and_multiple_sequences_fail_closed` in `test_meta_carousel_detail` indexes `cards[0]`, while the current normalizer correctly returns no cards for ambiguous labels. Executing the same fixture against the original revision also returns zero cards. This normalization behavior and test assertion were deliberately not changed. UI assertions that specifically required the removed arrows or old modal columns were updated to assert all cards/copy together; source/handoff contract assertions remain intact.

Final active-screen subset: 71 tests passed. Existing image clipboard regression script passed. Python compilation and scoped git diff whitespace checks passed.

Browser tests used the actual Streamlit render functions with explicit synthetic four-card fixtures, not live campaign evidence. All 12 strip cases (Review and Refresh) plus six actual Campaign Review modal cases passed at 1920×1080, 1440×900, 1366×768, 1024×768, 430×932 and 390×844. Checked card count/order, distinct fixture images, copy, no page overflow, manual selection, Apply, OPEN, image-copy fallback, ordered URL copying and zero Meta requests. Browser source interaction tests run without Graph access; active-screen tests separately assert a single cached creative resolution and complete four/five/six-card handoff.

Local evidence and screenshots: `.tmp-meta-carousel/ux-browser.json`, `ux-browser.log`, `ux-modal.log`, `ux-regressions.json`, `ux-final-active.log`, and `ux-*.png`.

## Live validation limitation

The environment and its existing dotenv configuration have no usable Meta token. **LAP OF GODS MOCKUPS was not read or live-verified.** A production operator still needs to open that real ad, confirm Dynamic Carousel · 4 cards, Apply, and verify its four actual images/copy in Refresh. No Meta mutations were made. No commit, push or deployment was performed for this UX task.
