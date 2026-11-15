# Files Performance V6

## Implementation and release status

Implemented in the existing `C:\Dev\SportsCaveWorktrees\sports-cave-files-performance-v1`
worktree, branch `codex/files-performance-v1`, Studio task `20261014-50508219`.
Base `c07119e425872300274559743f94a0f58586f201` matched main at the start and
contains V5 plus the legitimate Auto Editions archive changes. Its deployment
completed during this task. Latest inspected live Render revision is
`813ac3fc353bde6286a72d952dd4dcea58fd6e0e`, deployment `dep-db7l9re7bikc73d5epfg`,
live 14 October 2026 at 21:13 AEDT. That concurrent Auto Editions release is
untouched. V6 is committed locally for review, not pushed, integrated or deployed.
Reconcile against latest legitimate main and retest before release.

## Previous limits and new behavior

V5's fallback requested 1024×768 regardless of viewport/DPR. It assigned the next
image before decoding and refitted/reset pan on replacement. Folder opening had
a routine naming toast; the viewer also announced routine opening/preparing text.

V6 retains the cached 256 px thumbnail and requests an adaptive screen tier from
the actual viewport, rendered image size and device pixel ratio (capped at 3).
Tiers fit within **1024×768, 1600×1200 and 2048×1536**. Aspect ratio is preserved;
the cache processor never upscales smaller sources. The lightweight image can
fill the viewer while awaiting detail. Replacements decode asynchronously on a
detached image before becoming visible. Custom visual scale, pan and rotation
survive the replacement. Fit remains fit. Generation checks and cancellation
prevent a late image replacing another file or reopening a closed preview.

Zoom/resize requests more detail after a 160 ms debounce when a higher tier is
needed. One active preview request is retained. The full source still requires
Actual/1:1 or Download. No tile renderer was introduced: provider representations
top out at 2048×1536, so very high DPR/zoom can exceed available detail. The status
shows actual representation dimensions rather than claiming full source detail.

Fallback maps the two larger tiers to Dropbox's documented 2048×1536 representation;
small displays use 1024×768. The private pipeline stores high-quality WebP (quality
88, JPEG fallback), and a 256 px quality-76 thumbnail. Tagged local preparation
converts ICC colour to sRGB, preserving alpha before the existing white composite.
Originals are never rewritten. Provider-produced images retain provider quality
and colour handling, which remains subject to real artwork acceptance.

Private bundle keys include verified ID, revision, user/root, namespace and a new
processing version specifying all tier dimensions. One bundle supplies compatible
tiers without another original transfer. A 1024 provider asset can be upgraded
via the provider; that upgrade cannot download a second original. If an upgrade
fails, the lower asset remains usable. V5's bounded memory reuse, permission checks,
leases, encryption and cleanup remain. Oversized bundles omit intermediate sizes
before exceeding 4 MiB; those sizes derive from the retained sharp derivative and
enter the existing memory cache. The sharp derivative is never degraded just to
fit storage; an entry that still exceeds the budget fails safely.

**Ordinary requests cannot trigger background original downloads for files of
35,000,000 bytes or larger.** These need an existing prepared/provider asset.
Without one, show the accurate fallback; never quietly transfer the large original.
Smaller eligible sources retain capped one-time server preparation. The existing
explicit Actual transfer now seeds both 2048 and 1024 local previews from the same
stream, without fetching it again. No PSD source is downloaded/reconstructed for
preview. The direct preparation tests for large sources represent approved
preparation, not permission for an ordinary browser request to transfer them.

Removed the folder-opening toast and routine image/PDF opening/preparing footer
messages. Small affected-area placeholders and `aria-busy` remain, with actual
errors/confirmation notices preserved. No desktop helper or extra preview window
was restored.

## Measurements — synthetic, not Dropbox/R2

Evidence: `files-performance-v6-evidence/`. Actual Chrome, synthetic collector-text
JPEGs, 180 ms simulated network delay, 12 interleaved samples per version. p95 is
the largest observation at this small sample size, not a production percentile.

| Viewer stage | V5 p50 / p95 ms | V6 p50 / p95 ms |
|---|---:|---:|
| First lightweight image | 12.4 / 18.9 | 12.3 / 12.8 |
| Sharp image visible, from Open | 196.2 / 212.8 | 196.3 / 212.3 |
| Warm image reuse | 0.4 / 0.7 | 0.2 / 0.5 |

The sharp image replaced the thumbnail about 184 ms after it appeared, dominated
by the deliberately imposed 180 ms response delay. Median cold completion did
not improve; V6 adds adaptive quality and stable replacement, not a fabricated
provider speedup. Transfer and browser decode/render are included in these times;
the fixture does not model authentication, Dropbox or R2 latency separately.

The collector-text fixture has 20,297-byte thumbnail; 127,245 / 223,460 / 320,879-byte
JPEG screen tiers. A 1024→2048 zoom upgrade transfers another 320,879 bytes, with
zero originals. Two independent local flat/noise samples average 257 bytes small,
116,991 bytes at 1024, 355,247 at 1600, and 647,171 at 2048 after WebP preparation.
These are synthetic sample averages, not expected customer artwork sizes.
Encrypted bundle samples are about 19 KB and 3.96 MB. No production occupancy,
eviction rate or hit-rate measurements are available.

Encoded viewer cache remains 12 entries / 16 MiB / 30 seconds; backend memory
remains 128 representations / 32 MiB. Replacement temporarily needs old and new
decoded images (a 2048×1536 RGBA surface is about 12 MiB). The browser fixture
recorded about 3.11 MB JS heap / 334 nodes; this excludes native/GPU image memory.
No total memory reduction is claimed. Larger derivatives cost more CPU/storage;
preparation stays bounded to the existing background worker and never blocks the
viewer controls. Intermediate-size compaction preserves the namespace's storage
bound rather than increasing it.

Broader browser acceptance: 2,000-item cold list 102/111→101/109 ms; cached folder
6.7/8.1→6.6/7.3 ms; shell 24.2/25.4→25.2/29.4 ms. Launcher single samples 115→87 ms,
warm reopening zero additional listings. Open-preview journey 77/95→76/95 ms;
close/reopen journey 26/29→29/30 ms. Scrolling 16.7/16.8 ms; exact archived JPG
selection 122 ms. All are simulated-provider timings.

The separate standalone four-sample cold viewer result is slower, 79/80→95/111 ms;
warm 0.9/1.0→0.6/0.7 ms. Results are retained. Async predecode deliberately waits
for usable pixels before replacement. The controlled interleaved progressive test
above does not reproduce a material transition delay. No overall end-to-end
speed improvement is claimed. Higher quality trades some transfer/processing for
detail; the small tier avoids paying that on every display.

## Provider/cache blockers and acceptance

No safe non-production Dropbox/R2 account is configured locally. The value-free
configuration report shows all local `FILES_PREVIEW_*` and R2 connection settings
absent. Production environment configuration cannot be read through the available
connector. Prior authorised Render metrics/log queries yielded no usable Files
data. Persistent activation remains **unknown remotely and disabled locally**;
it was not activated here. Do not infer activation from deployed code.

Administrator requirements remain those in `FILES_PERFORMANCE_V5.md`: confirm an
existing private bucket, namespace, valid shared Fernet key, bucket-scoped R2
credentials/endpoint, conditional writes/leases, failure recovery and cleanup in
a synthetic namespace. Run `scripts/files_preview_status.py` in the intended
environment without disclosing values, then perform authorised real-provider
acceptance before enabling `FILES_PREVIEW_PRIVATE_BUCKET_CONFIRMED=1`.
No infrastructure was created and no production credentials/customer artwork used.

Dropbox documents only up to 2048×1536 and its thumbnail API has source-format/
size limits. Large JPG and PSD availability therefore cannot be guaranteed by
this fallback. Persistent prepared assets or an explicit original operation are
needed when the provider cannot supply a suitable image. Real cold/warm latency,
plaque/text/faces quality and colour fidelity remain unverified on customer-like
authorised artwork. See [official Dropbox size documentation](https://dropbox-sdk-python.readthedocs.io/en/latest/api/files.html#dropbox.files.ThumbnailSize)
and [thumbnail endpoint documentation](https://dropbox-sdk-python.readthedocs.io/en/latest/api/dropbox.html#dropbox.dropbox_client.Dropbox.files_get_thumbnail).

179 offline tests pass across the full suite and final focused reruns. Acceptance
covers progressive stages, geometry retention, DPR selection, zoom
upgrade, revisions, close/switch cancellation, permissions, cached navigation,
large lists, supported PSD/unsupported fallbacks, PDF, Actual, Download, uploads
and all existing file-management operations. Four web-only platform journeys,
Orders desktop/mobile exact selection, and nine shared PSD-modal scenarios pass.
Preservation tests now use the legitimate V5/live base for shared files; this
accommodates the already merged Auto Editions archive work, not V6 edits to it.

Auto Editions generation, originals, masters, allocations, mappings, archives,
Design/Developer Studio, Windows preparation host, Shopify and Prodigi are
unchanged by V6. Review-ready locally; deployment/private-cache activation remain
on hold pending provider validation and reconciliation with newer main.
