# Meta Review carousel repair — 7 October 2026

## Status

Code repair implemented locally; live Warne Graph verification remains required.

**LIVE META VERIFICATION REQUIRED AFTER DEPLOY.** Nothing was committed, pushed or deployed. No live Meta mutation occurred. No real campaign or ad was changed. The process environment and project `.env`, loaded using the existing configuration reader, returned `configured: false` and `access_token_present: false`. No Meta connector is available in this session. Therefore no real Warne creative ID, card images or copy could be verified here.

## Findings in the current checkout

`build_carousel_creative_payload()` in `meta_posting_service.py` is unchanged. It authors exactly five `object_story_spec.link_data.child_attachments`, each with image hash, headline, description, destination and CTA; its five Primary Text variations are separate `asset_feed_spec.bodies`.

The current normalizer already gives genuine inline children precedence over the mere presence of an asset feed. Consequently, the suspected blanket `asset_feed_spec => ignore inline cards` bug was **not reproduced in this checkout**. Its presence in a deployed version, or the exact cause of Warne's live failure, cannot be asserted without the real read.

Confirmed gaps repaired:

- The live resolver previously skipped the story read whenever `source_cards(raw)` found *any* source, including the lower-priority asset-feed sequence. It now tests specifically for genuine inline cards before deciding whether to read the story.
- Asset-feed labels with missing or multiple matches produced partial cards instead of rejecting the ambiguous sequence, including potentially mismatched or missing card copy.
- A partial story could be discarded and silently replaced with a lower-priority feed sequence. Incomplete pagination now fails closed.
- Shared Primary Text variations had no explicit normalized/handoff pool. The screen could replace the pool with one shared message. Every valid variation now survives separately.
- The selected viewer preferred a card thumbnail over its resolved image. It now shows that card's resolved image.
- Handoff and Refresh validated positions/images but not the authoritative source count. A truncated sequence could pass after losing a final card. Both now compare counts, allowing only the explicitly excluded Meta Page/profile end card.
- A failed selected-creative read could leave a representative image available for an unsupported carousel handoff. Known carousel/dynamic failures are now blocked.

## Active path and precedence

Campaign/ad metadata → `build_ads()` → selected `resolve_selected()` → bounded, scoped cache → `creative.resolve()` → full creative GET → source resolution → one batched adimages query (bounded pagination if returned) → `apply_resolved()` → local fragment viewer → `build_package()` → unchanged archive/action-log persistence → hydrated source winner → `reference_map()`.

Resolution order:

1. Multiple genuine inline `object_story_spec.link_data.child_attachments`, retaining all original positions, even if another card is incomplete. `asset_feed_spec.bodies` never removes these cards.
2. Effective story, otherwise object story, attachments/subattachments. Returned nested pagination is inspected. Any `paging.next` fails closed rather than declaring a partial sequence complete. More than one competing subattachment sequence also fails closed. A single cover is never a carousel.
3. One explicit asset-feed carousel. Each provided image/title/description/link/video label must match exactly one corresponding asset. Missing/duplicate label matches and ambiguous media are rejected. Generic pools are never paired or sliced into cards.
4. No confirmed carousel sequence. Unknown evidence stays unknown; generic dynamic/video classification remains compatible with existing behavior. Explicit incomplete carousel evidence blocks Refresh.

Cards retain authored/source positions, image hash/URL, source/attachment identity, creative/ad identity, headline, description, destination, CTA (including returned structured CTA), and video ID where provided. All required image hashes are collected before the account `adimages` GET and mapped strictly by hash, not response order. No creative-level thumbnail fills absent cards.

## UI, handoff and performance

Confirmed mixed inline/feed sources display **Dynamic Carousel · 5 cards**; plain fixed sources display **Carousel · 5 cards**. Both map to **Carousel** in Creative Refresh.

The viewer remains a Streamlit fragment with local previous/next state. Each visible card has its own resolved image and copy. “Shared Primary Text” is a separate expander containing all valid variations. The optimization note explains that authored source order is shown even when Meta optimizes delivery order.

The selected viewer index is not an input to the handoff. APPLY while viewing Card 3 still carries Cards 1–5 and all shared Primary Text. Existing persistence archives each unique card URL and retains every card's archive reference. Refresh receives WINNER_CARD_1 through WINNER_CARD_5 plus CANONICAL_PRODUCT. Existing prompt authority rules remain unchanged: canonical black-frame artwork is product authority; winning cards supply environment/composition authority.

Campaign/ad list loading, benchmarks, metrics, Posting and New Ads were not edited. Full creative/image-hash resolution remains selected-ad-only. Cache scope still includes account, API version and credential-context hash; the creative cache namespace was advanced to `creative-v3`. Arrows make no Graph requests. Images may load in the browser when their card is first shown.

## Safe diagnostic

The existing selected-ad screen and winner area expose an **admin-only Advanced Meta diagnostic** using the existing account-role check. Normal logs also contain allowlisted structural information, never raw Graph responses, tokens, headers, secret environment values or image bytes.

Fields:

```text
campaign_id
ad_id
creative_id
object_story_spec_present
inline_child_attachment_count
effective_object_story_id_present
story_attachment_count
story_subattachment_count
story_pagination_complete
asset_feed_spec_present
asset_feed_carousel_group_count
asset_feed_carousel_child_count
image_hash_count
resolved_image_count
detected_format
format_source
source_card_count
normalized_card_count
resolved_card_count
displayed_card_count
handoff_card_count
```

`displayed_card_count` is the complete navigable set, not the number of simultaneously visible images. `handoff_card_count` is zero until successful APPLY for that ad/source in the current session. `story_pagination_complete` is null when no story read was needed, true for a complete returned edge, and false when a further page prevents certification.

## Verification

21 regression modules, **470 tests passed**, zero failures/errors/skips. These include Meta Review, reporting/benchmark metrics, Creative Refresh, Posting, five-card carousel Posting, Instant Experience, Single Image, Video/dynamic and New Ads default behavior. After the final diagnostic-count adjustment, all **15 new contract tests** passed again.

The active-screen contract test uses the real Posting builder and patches only Graph/storage boundaries. It verifies shuffled hashes, all individual card copy, five shared texts, arrows 1→5→1 with no additional Graph calls, then APPLY from Card 3. Separate tests verify archive/hydration, missing and truncated sources, story precedence/pagination, deterministic/ambiguous asset labels, video identity, admin-only diagnostics and failed selected reads.

Python compilation passed for the changed files and relevant Meta Review/Refresh/Posting modules. `git diff --check` passed. Git reported existing Windows CRLF normalization notices, not whitespace errors. No unrelated test failures occurred in the suites run; the entire repository test suite was not run. Pre-existing unrelated working-tree changes were preserved.

Local logs: `.tmp-meta-carousel/regressions.log`, `.tmp-meta-carousel/results.json`, `.tmp-meta-carousel/targeted-final.log`.

| Count | Posting-contract test | Real Warne |
|---|---:|---|
| Source | 5 | Not read |
| Normalized | 5 | Not read |
| Resolved images | 5 distinct images | Not read |
| Displayed/navigable | 5 | Not read |
| Handoff | 5 | Not read |

## Live Warne acceptance after a separately authorized deployment

1. In Sports Cave OS, open **Warne 181125 → Carousel Shane Warne**. Selection itself performs the full read; Graph Explorer is unnecessary.
2. As an admin, inspect Advanced Meta diagnostic. Confirm actual campaign/ad/creative IDs and the authoritative `format_source`.
3. If Meta returns the Posting inline contract, expect inline count 5, asset feed present, image hash count 5, source/normalized/resolved/displayed counts 5, and Dynamic Carousel as the detected format. Story counters may be zero/null because inline wins. A legitimate story fallback may have different structural counters but must still produce the complete five cards.
4. Inspect all five distinct images and their corresponding headline/description/destination/CTA. Confirm the five Primary Text variations appear separately. Traverse 1→5→1; no new Graph creative/hash reads should occur.
5. View Card 3 and APPLY. Confirm handoff count 5 and five archived WINNER_CARD references in Creative Refresh, plus the separate canonical product reference.
6. Any missing image, incomplete pagination, ambiguous sequence or failed full read must prevent an incomplete carousel refresh.

## Files changed

- `meta_review_creative.py`
- `ads_meta_review_page.py`
- `meta_review_handoff.py`
- `ads_refresh_plan.py`
- `tests/test_meta_review_carousel_contract.py` (new)
- `docs/META_REVIEW_CAROUSEL_REPAIR.md` (this report)
