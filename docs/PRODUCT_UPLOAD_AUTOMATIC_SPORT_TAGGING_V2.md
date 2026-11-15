# Product Upload automatic sport tagging V2

Implemented locally on 11 October 2026. **Not committed, pushed or deployed. No live Shopify test products, tag writes, customer changes or consent changes.**

## Existing system inspected

The existing page is `render_product_uploads_page` in `app.py` (around line 9745), displayed as **Shopify Prompt Tools**. Its three choices remain:

| Existing choice | Purpose | Definition / assembly |
|---|---|---|
| UPLOAD TO DRAFT | Build a complete unpublished Draft with normal images, variants, prices and QA | `NEW_SHOPIFY_PRODUCT_PROMPT`, `app.py:520`; `product_upload_modes.DRAFT_FINAL` |
| UPLOAD & PUBLISH LIVE | Same staging build, then the existing explicit confirmation, QA, inventory/publication/Market checks | Same existing new-product constant; `product_upload_modes.LIVE_FINAL` |
| Update existing product | Update the verified existing ID within its current media/copy/pricing scope safeguards | `UPDATE_EXISTING_PRODUCT_PROMPT`, `app.py:1014` |

`get_product_upload_prompt` / `build_product_upload_prompt` route all three through `apply_product_upload_prompt_updates`. The two original large prompt constants remain byte-for-byte identical to deployed HEAD. The existing shared finalizer now appends one generated V2 policy. Saved overrides have the previous V2 block stripped and regenerated, so repeated application is stable and all modes receive the same current policy.

This is an **exported-prompt workflow**, not a local Shopify product editor: the user copies the prompt into the connected assistant, which performs creation/update. There is no existing local productCreate/productUpdate upload function to wrap. Collection selection likewise happens in the exported workflow: `product_upload_collections.py` discovers the complete catalogue, matches sport/athlete/event collections, and retains manual/automatic collection rules and publication safeguards. The collection selector and page layout are unchanged.

After this architectural finding, the user explicitly selected: **“Add a tagging-only backend hook to the existing product webhook workflow, preserving the prompt page.”** The implementation follows that decision. It does not add another uploader, UI, service, API route or customer-segment system.

## Shared classification

`product_sport_tags.py` owns the exact tag mapping, collection labels, curated subject fallbacks, hierarchy, conflict checks, deduplication and preservation. The prompt block and its local advisory preview come from this module. The independent webhook adapter calls the same classifier against fresh Shopify data.

Evidence order and handling:

1. Match exact collection title/handle, including known existing catalogue handles and exact curated athlete collections. Do not classify by loose collection substrings.
2. Combine verified structured sports/events/competition context when supplied to the pure classifier; exact competition labels in the product title supplement collection evidence.
3. Use curated athlete history only as a fallback. Specific depicted motorsport context overrides that fallback. Athlete collections use the same identities; the existing audited basketball/football collection identities are reused.
4. Descriptions cannot add arbitrary new sport tags. A conflicting precise motorsport reference in description copy triggers review, preventing an incorrect career-based fallback. This deliberately resists variable AI marketing copy and unverified biography.
5. Genuine multiple subjects, explicit sports or relevant collection memberships can yield multiple sports. Contrary collection/event/subject evidence triggers review rather than an automatic union of incompatible claims.

Generic Champion, GOAT, Racing, Legend and Final have no mapping. Bare Rugby and Hockey do not resolve League/Union or ice/field hockey. Promotional collections—All Sports Wall Art, Best Selling Sports Wall Art, Popular, Featured Designs, Collector Series, New Products, The Gift Edit and Rivalries—provide no sport evidence. No collection membership is changed to force classification.

## Complete tag / collection mapping

Exact sport labels and the same labels followed by “Wall Art” are supported. Handles are normalized for spaces/hyphens and accents; known live catalogue aliases are listed below. IDs are always obtained from Shopify, never manufactured.

| Sport/category | Exact Shopify tag | Additional exact labels / collection handles |
|---|---|---|
| Motorsport | SC_SPORT_MOTORSPORT | Motor Racing, Motorsports, Motor Sports; motor-racing-wall-art |
| Formula One | SC_SPORT_FORMULA_ONE | F1, Formula 1; formula-one-wall-art |
| NASCAR | SC_SPORT_NASCAR | nascar-wall-art |
| V8 Supercars | SC_SPORT_V8_SUPERCARS | Australian Supercars, Australian Touring Car Championship, ATCC, Bathurst 1000; v8-supercars-wall-art |
| MotoGP | SC_SPORT_MOTOGP | Motorcycle Grand Prix, 500cc Grand Prix; motogp-wall-art |
| Motocross | SC_SPORT_MOTOCROSS | Supercross; motocross-wall-art; Jett Lawrence |
| Rally | SC_SPORT_RALLY | WRC, RAC Rally; rally-wall-art; Colin McRae |
| Motorcycle Road Racing | SC_SPORT_MOTORCYCLE_ROAD_RACING | Isle of Man TT; motorcycle-road-racing-wall-art; Michael Dunlop |
| Rally Raid | SC_SPORT_RALLY_RAID | Dakar, Dakar Rally; rally-raid-wall-art; Toby Price |
| IndyCar | SC_SPORT_INDYCAR | Indy 500, Indianapolis 500; indycar-wall-art; Will Power |
| Basketball | SC_SPORT_BASKETBALL | NBA; nba, basketball-wall-art |
| NFL | SC_SPORT_NFL | American Football; nfl-wall-art |
| Baseball | SC_SPORT_BASEBALL | MLB; baseball-wall-art |
| Ice Hockey | SC_SPORT_ICE_HOCKEY | NHL; ice-hockey-wall-art |
| Cricket | SC_SPORT_CRICKET | cricket |
| Football | SC_SPORT_FOOTBALL | Soccer, Association Football; soccer |
| Rugby League | SC_SPORT_RUGBY_LEAGUE | NRL; rugby-league-collection |
| Rugby Union | SC_SPORT_RUGBY_UNION | rugby-union-wall-art |
| AFL | SC_SPORT_AFL | Australian Rules Football, Australian Football, Aussie Rules; afl-wall-art |
| Tennis | SC_SPORT_TENNIS | tennis-wall-art |
| Golf | SC_SPORT_GOLF | golf-wall-art |
| Horse Racing | SC_SPORT_HORSE_RACING | Thoroughbred Racing; horse-racing-wall-art |
| Combat | SC_SPORT_COMBAT | Combat Sports, Boxing, MMA, UFC, Mixed Martial Arts; combat-art |
| WWE | SC_SPORT_WWE | wwe-wall-art |
| Athletics | SC_SPORT_ATHLETICS | Track and Field; athletics-wall-art |
| Olympics | SC_SPORT_OLYMPICS | Olympic, Olympic Games; olympics-wall-art |
| Surfing | SC_SPORT_SURFING | surfing-wall-art |
| Apparel | SC_CATEGORY_APPAREL | apparel-wall-art / exact Apparel collection, productType Apparel or Clothing |

All nine motorsport subcategories above also require `SC_SPORT_MOTORSPORT`. WWE also requires `SC_SPORT_COMBAT`. No other tag convention is introduced. Athletics is not a generic Olympic category; Olympic swimming yields Olympics, not Athletics. Swimming has no invented sport tag.

Other recognized motorsport—sports-car/GT/endurance/Le Mans/Bathurst 12 Hour racing, Superbike/WSBK, Enduro, Speedway, Karting, Drag Racing, Motorcycle Endurance/Suzuka 8 Hours, Supermoto and Hill Climb—yields only Motorsport. It does not inherit a driver's Formula One/MotoGP/etc. career tag. Dakar is Rally Raid rather than Rally; Isle of Man TT is Motorcycle Road Racing rather than MotoGP. Exact depicted competition overrides athlete history. The five additional named athletes above also support exact athlete collection matching.

Curated subject fallbacks cover all requested examples: Peter Brock, Allan Moffat, Dick Johnson, Craig Lowndes, Jamie Whincup; Ayrton Senna, Lewis Hamilton, Max Verstappen, Oscar Piastri, Michael Schumacher, Daniel Ricciardo; Dale Earnhardt/Sr., Jeff Gordon, Kyle Larson, Richard Petty, Jimmie Johnson, Bill Elliott; Valentino Rossi, Marc Márquez, Casey Stoner, Mick Doohan, Jorge Lorenzo; Michael Jordan, Shane Warne, Tom Brady, Andrew Johns, Cristiano Ronaldo, Winx and Undertaker. Existing audited collections additionally supply LeBron James, Stephen Curry, Kobe Bryant and Lionel Messi. This is intentionally a curated map, not a claim to know every athlete or vehicle. Unknown identities require verified sport collections/context or review.

Historical Australian touring cars/Bathurst 1000 use V8 Supercars for marketing classification without rewriting the historical title, event, vehicle or description.

## Shopify save integration and failure handling

The prompts require classification before the normal create/update, merging required tags with existing tags and verifying the saved result. Existing-product Media Update Mode explicitly permits these additive tags while retaining every other scope restriction.

For deterministic backend enforcement, the existing authenticated `products/create` and `products/update` routes call the existing `process_product_create_webhook` processor. Its receipt claim, duplicate detection, HMAC handling and failed-delivery retry lifecycle remain in place. Both Draft and Active products pass through `product_sport_tag_sync.sync_product_sport_tags`.

The adapter uses the existing `shopify_sync.graphql_request` authentication/configuration. It reads the exact product ID, title, description, product type, tags and **all collection pages**, classifies fresh evidence, and performs only additive `tagsAdd` for missing approved tags. It never uses a stale webhook snapshot for classification and never replaces the product tag array. Fresh readback must prove all expected/preserved tags exist; mutation success alone is insufficient. Page inconsistency, repeated cursors, missing product, API errors, unknown mutation identity and readback failures are errors.

Two bounded attempts reconcile uncertain timeout outcomes by rereading the same ID. Already-applied tags produce no further mutation. There is no product creation/replacement in the adapter. Concurrent additive operations cannot overwrite other tags. A later webhook from the tag change becomes a read-only no-op when tags are already correct.

Unknown/conflicting classifications produce `review_required`, write no uncertain tags, and persist reasons in existing webhook event warnings and last-product-webhook diagnostics. The HTTP result includes `sport_tagging`; no new schema or UI is needed. An old established sport tag that is not supported by the new evidence remains untouched and requires controlled correction. No automatic removal is implemented.

Transient failures mark the existing receipt failed for retry and return an error rather than success. Existing active-product Edition Ops registration still runs when tagging is unavailable, so tagging does not starve edition/certificate readiness. Repeated registration retains existing ledger counters/history. Draft products remain Draft and do not get an edition allocation as a side effect of tagging.

This hook is asynchronous and applies to the existing product webhook stream, including product edits outside the prompt page. It does not run on merely viewing an existing product. Tag verification in the exported prompt remains the completion/publication gate; a webhook response or productCreate response alone cannot prove completion. No remote assistant can be forced by this repository to follow a prompt, and the hook cannot prevent an external assistant from making a bad write before the webhook arrives. It provides deterministic additive enforcement after a supported product save, not a new synchronous upload transaction.

Shopify operations were schema-validated against Admin GraphQL **2026-04**. Documentation: [tagsAdd](https://shopify.dev/docs/api/admin-graphql/2026-04/mutations/tagsAdd), [Product](https://shopify.dev/docs/api/admin-graphql/2026-04/objects/Product). Live access scopes were not changed or exercised.

## Verification

Combined V2/V8 final extension: **69 focused tests pass, zero skips**, including the
original 67 tests updated for the new categories and two additional regression
methods. All 28 tags and all nine motorsport disciplines are exercised. The real
webhook path verifies additive writes and duplicate retries for every motorsport
child. All three prompt modes still preserve their original content outside the
appended policy. The broader final run has **207 tests, 13 baseline failing
assertions and 16 existing skips**. Re-running the 181-test deployed-source
baseline reproduces those same 13 failures and 16 skips. No new broad-suite failure.
The original verification below is retained as implementation history.

- **67 focused tests passed, zero skips**: all twelve requested artwork cases; all 23 exact tags; broad/precise motorsport and history; multiple collections/sports; Olympic swimming; unrelated and established tags; unknown/conflicting evidence; all three real prompt builders; saved-prompt idempotence; new Draft / existing Active webhook processing; timeout after accepted mutation; duplicate retry/receipt; user errors; readback missing tags/failure; pagination failure; preservation of variants/images/prices/descriptions; Edition Ops counter/history preservation and registration during a tagging outage.
- Both GraphQL operations validated successfully, including separate validation of the additive mutation.
- Original new/existing prompt constants are identical to deployed HEAD. For all three modes, stripping the appended V2 block yields the exact pre-change generated content.
- The broader suite ran **205 tests**. It retains **13 failing subtest assertions across four pre-existing pricing/copy tests**, reproduced with deployed `HEAD:app.py`, and **16 already-retired allocator tests are explicitly skipped**. No new failure was introduced. This broad run is not described as green.
- Existing fixture maintenance: corrected stale deployed prompt hashes, added the current page's `title` method to the UI fake, excluded the appended policy from historical content-only comparisons, and mocked the separate tag adapter in existing edition-only tests. Dedicated integration tests exercise the real adapter with in-memory Shopify and ledger fixtures.
- All requests in execution tests were mocked or local-only, with credentials stripped and external socket connections blocked. Raw evidence is under `.tmp-product-sport-tags-v2/`.

The four pre-existing failing test methods are `test_previous_framed_prices_and_saved_exception_are_upgraded`, `test_saved_all_framed_rrp_exception_is_replaced_by_price_only_scope`, `test_saved_supplemental_pricing_tables_are_updated_in_all_three_modes`, and `test_both_actual_builders_share_rules_and_research`. They expose stale saved pricing-exception/copy text handling, including the old “exactly four paragraphs” wording. Repairing unrelated price/copy behavior is outside this change; those failures should be reviewed before a broad all-green release claim.

## Files changed

- `product_sport_tags.py` — new shared deterministic policy/classifier and generated prompt block.
- `product_sport_tag_sync.py` — new tag-only Shopify transport adapter and readback.
- `app.py` — two small Product Upload-only integration hunks; existing Inbox hunk preserved.
- `supabase_backend.py` — tag hook, warnings and retry handling in existing product webhook processor.
- `webhook_server.py` — expose tagging outcome in existing product webhook response.
- `tests/test_product_sport_tags.py`, `tests/test_product_sport_tag_integration.py` — new tests.
- `tests/test_product_upload_prompts.py`, `tests/test_product_activation_sync.py`, `tests/test_product_webhook_restoration.py`, `tests/test_shopify_sync.py` — fixture isolation / regression maintenance.
- This report.

No modifications to prompt pricing/media/publication logic, collection selection, inventory operations, edition allocation, certificate implementation, customer segments, consent or Email Inbox implementation.

## Review examples and deployment requirements

Review examples: Senna in an NBA or NASCAR collection; Rossi GT artwork in MotoGP; a contrary precise series in description copy; a product with an old Formula One tag now presented as Peter Brock; bare “Rugby Legend”; unknown athlete with promotional collections only; a sport without an existing supported Shopify tag. Review preserves current tags and reports the evidence rather than guessing or removing historical classification.

1. Review this local change before authorizing any release. No release manifest was prepared, no Git history changed, and no automatic deployment is scheduled.
2. **`app.py` also contains unfinished Inbox work. Do not deploy its entire current working contents or use Inbox approval to bypass the hold.** Isolate only the two Product Upload hunks against the verified production baseline, or wait until the separate Inbox work is explicitly approved. A local review patch is saved under `.tmp-product-sport-tags-v2/product-upload-v2.patch` to identify this change independently; it does not authorize a release.
3. Confirm existing product-create/update webhook subscriptions are healthy and the existing app credentials have `read_products` and `write_products`. No new service, subscription or environment variable is required by this implementation. Use the existing configured API version; operations were validated for 2026-04. Missing permissions/readback must not be bypassed.
4. Deploy prompt and webhook changes together through the existing canonical Sports Cave services when approved. No database migration, customer-segment rewrite or bulk tag backfill is part of this release.
5. Review the pre-existing broad-regression failures above. Do not silently skip them or present the full suite as passing.
6. After a separately authorized release, verify the first genuine product operation through normal saved-product tag readback and webhook diagnostics. Live test products need separate approval.

Existing sport tags and customer/segment records are never removed or rewritten. Adding missing product tags is intended to supply the existing purchase-based segment rules; this code does not promise that dynamic Shopify segment membership is frozen when product metadata changes.
