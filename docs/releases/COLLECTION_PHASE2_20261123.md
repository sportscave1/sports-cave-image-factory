# My Collection performance phase 2 — local only

Task `20261123-2509a89b`, owner `codex-collection-phase2-20261123`.
Base: `daec97e570fb6abcbff7a9245c798a64ff6f92e9` (latest production certificate design).
Phase 1's uncommitted changes are included in this isolated working copy; its original worktree remains unchanged. No commit, push, deployment, production storage write, real review or customer automation was performed.

## Customer decisions

- The review section now says **Add photo/video (optional)**. Account photos keep the existing image-only upload, validation and Judge.me submission path. **Add video** opens the existing storefront reviews page in a new tab. The accompanying text directs the customer to **Write a review** and to complete their video review there. It does not auto-open or auto-submit the storefront form, nor copy personal information or unfinished account form fields into a URL. No new theme embed is required.
- Keep Shopify's native edition browser. Swiping still needs a tap to select; arrows continue to select directly. Automatic selection on swipe was explicitly deferred by the user after reviewing Shopify's event limitations. No unsupported swipe event handler or account platform migration was introduced.

Platform references: [Shopify native ScrollBox events](https://shopify.dev/docs/api/customer-account-ui-extensions/2026-04/web-components/layout-and-structure/scroll-box), [Judge.me API video restrictions](https://judge.me/help/en/articles/8409180-using-judge-me-api).

## Preview pipeline

The asset endpoint validates the existing signed token and resolves current certificate ownership from the database on every request, before accessing any cached bytes. This lookup, source downloads and Pillow rendering run in the existing thread pool rather than blocking the async request loop.

The process-local cache holds up to 16 MiB / 32 source entries and 8 MiB / 96 derived previews, with five-minute expiry and LRU eviction. Retained encoded bytes are bounded to 24 MiB per process; transient download buffers, decoded images and Python object overhead are additional. Up to two downloads and one composition can run concurrently per process. Unique pending loads are bounded to 12 per cache; identical in-flight requests share a result. Saturation returns a temporary-unavailable response; failed loads can be retried.

Source identity includes the verified owner, certificate row, stored locator and row revision. Output identity additionally includes frame colour, width, geometry, recipe version and frame-template size/mtime. Fresh signed browser tokens can reuse an authorized issued asset without becoming cache keys. R2 download URLs are generated only on a source-cache miss. Failed composition evicts its source so a corrupt download does not stay cached.

All three frame colours reuse one original source download. Completed colour/size previews avoid further download/composition while cached. Responsive images advertise 400px and 1000px WebP variants; the existing black prewarm uses the same sizes as the popup. Browser viewport and pixel density determine which variant is requested. Older clients retain the 1000px default. The existing OS frame placement and full-certificate containment are preserved.

This is lazy, private, in-memory caching. It is not persistent pre-generation: cold assets and new/restarted workers still perform initial work, and separate workers maintain separate caches. There is no shared Redis cache, new Render service, database migration or R2 write.

## Preserved behavior

Only derived frame previews are resized/cached. Originals are read from the already-issued certificate assets, never regenerated from the latest blank master. Numbering, existing customer certificates, printable JPG/PDF downloads, cart/pricing checks, recommendation ranking, order submission and multi-item supplier processing are unchanged. The Phase 1 work already separates optional review loading, trims recommendation data and sizes public thumbnails; recommendation caching and real-user performance instrumentation remain later phases.

## Offline evidence

`python scripts/benchmark_collection_previews.py` uses a synthetic certificate and real local frame templates/Pillow. It performs one cold pass and five warm passes for each size; it excludes database authorization, actual network latency and browser rendering.

| Three frame colours | 400px | 1000px |
| --- | ---: | ---: |
| Cold pipeline | 150.069 ms | 389.338 ms |
| Warm pipeline median | 0.532 ms | 0.567 ms |
| Combined output bytes | 29,532 | 178,648 |
| Source fetches across all six passes | 1 | 1 |
| Compositions across all six passes | 3 | 3 |

The synthetic 400px outputs are approximately 83.5% smaller. These are not live page-load measurements or SEO scores. Authenticated account improvements concern customer experience; public storefront indexing is unaffected.

## Validation and limitations

- 19 new Phase 2 Python checks pass: TTL/LRU/byte limits, deterministic concurrent deduplication, failures/retry, owner/certificate/revision separation, recipe/size invalidation, expired signatures, real signed ownership resolution, API authorization on warm hits, source limits/closure, responsive rendering with intact corners, invalid option rejection and an independently running async coroutine during blocked rendering.
- The focused Phase 1/2, offers, pairing and print-download suite passes 42 tests plus 3 subtests.
- 39 Node checks pass, including the separate video route, photo-only upload, responsive signed preview URLs, native edition navigation, purchased variants, multi-item image mapping, cart preservation and smart pair ordering.
- Native project TypeScript, Shopify app configuration and Shopify production build pass locally. The standalone Shopify Toolkit component validator cannot start because its own installation lacks `typescript`; the project compiler/build are available and pass.
- The broader Python regression run records 148 passed, 17 subtests passed, 10 skipped and 9 existing failures. Seven old source assertions in `test_customer_certificate_vault.py` also fail when reads are substituted with `git show HEAD:<path>`. Two `get_user` subtest failures in `test_account_read_queries.py` reproduce with HEAD's unchanged `os_accounts.py`; `supabase_backend.py` and those tests are untouched. These failures have not been hidden or rewritten as part of this task.
- The ten skips include opt-in database/integration checks without local prerequisites. No production credentials or live customer data were used for development previews. Local browser preview remains disabled by Studio rules.

Evidence: `C:/Dev/SportsCaveWorktrees/.studio/runtime/20261123-2509a89b/` (`python-regression.log`, `preview-benchmark.json`, plus focused/build/static logs).

Automatic approval review rejected cleanup of the local generated account manifest and automation-pixel build directory. They remain in this task's worktree; no alternate deletion method was used.

## Future release

This work remains uncommitted and local as requested. A later authorized release must publish the backend to the existing canonical Sports Cave OS service before the account extension, then verify real mobile/desktop display and cold/warm timings without sending a real review or placing an order. Existing certificates require no regeneration or backfill. No release is authorized by this document.
