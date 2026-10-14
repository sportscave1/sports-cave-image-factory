# Files V6 — compact presentation

Continues V6 in `C:\Dev\SportsCaveWorktrees\sports-cave-files-performance-v1`,
branch `codex/files-performance-v1`, Studio task `20261014-50508219`.
Baseline: `e021e88b`. Only the existing Files window's presentation/row handling,
browser tests and evidence changed. No second application, new dependency,
backend change, original artwork modification or storage activation.

## Presentation

| Item | Before | After |
|---|---:|---:|
| Default icon box | 90 px | 48 px desktop, 40 px narrow container |
| Large/comfortable icon box | 118 px | 56 px |
| Default grid cell height | 142 px | 100 px desktop, 92 px narrow |
| Comfortable cell height | 174 px | 112 px |
| Row / column gap | 12 / 8 px | 6 / 6 px |
| Columns at 1280 px | 8 | 10 |
| Detail/list icon box | 32 px | 24 px |

The folder SVG uses a restrained gold fill and consistent rounded geometry.
Other file types retain their recognisable existing icons and matching fixed-size
containers. Thumbnails retain `object-fit: contain`, stable placeholders, lazy
loading and cached attachment. No large artwork is fetched for these icons.

Names use consistent 13 px text, centred beneath grid icons, clamped to two lines
with ellipsis. Full names remain in tooltips, accessible labels and unchanged
operation metadata. List/details use single-line ellipsis and aligned metadata.
Details/List rows remain approximately 38 px under the existing shared table theme;
touch rows are 44 px. The existing light theme is retained; no unsupported dark
theme was introduced.

View menu labels are now **Compact icons** and **Comfortable icons**, reusing the
existing `medium`/`large` preference keys. Default remains `medium` (now compact).
Saved user preferences are respected. Small icons, List and Details remain.
No additional settings UI. View changes no longer show a routine confirmation
toast; V6's removed opening notices stay removed.

CSS Grid calculates columns from the content container. A container query reduces
icon/cell dimensions in narrow windows. Virtualisation measures that same CSS,
so normal and large-folder layouts agree. Compact grids keep one buffered row
instead of two to limit extra offscreen DOM work. Unchanged metadata objects
reuse rows without repeated serialization. Thumbnail updates do not rebuild rows.

Hover stays subtle, selection stays blue, and focus has a clear inset 2 px outline.
Up/Down moves by the measured grid row; Left/Right moves by item. Shift selection,
multi-selection and context menus remain. Toolbar labels remain accessible when
visually hidden. Narrow toolbars wrap rather than clipping controls; coarse-pointer
buttons/menu actions have 44 px hit targets. Narrow List/Details hide secondary
columns that cannot fit, retaining names and accessible full item information.

## Browser/visual acceptance

Actual Chrome, synthetic content only; no production credentials or artwork.
All five views were checked at widths 320, 375, 768, 1024, 1280, 1440 and 1920.
No horizontal content overflow, overlapping names or clipped row contents.
Default columns: **3, 3, 6, 8, 10, 11, 15** respectively. Tested popup resizing,
both 20-item normal and 2,000-item virtual lists, long names, focus, selection,
context menu and persisted view. A 375 px coarse-touch/DPR-3 viewport passes tap
target checks. These cover Windows/Mac-sized desktop, laptop, tablet and phone
dimensions in Chromium; they are not native Safari/macOS or Android device tests.

- 179 offline regression tests pass.
- Four browser platform journeys pass: internal image/PSD/PDF previews, all Open
  actions, create/rename/delete/copy/move/search, uploads/downloads and permissions.
- Thumbnail tests pass: no layout shift, immediate cached attachment, four live
  requests maximum, cancellation and revision/account isolation.
- V6 progressive decode/upgrade/zoom geometry tests pass unchanged.
- Orders desktop/mobile tests pass: exact archived JPG, preserved Orders state,
  downloads and duplicate-open protection. No Files helper windows or requests.

The renamed-toolbar accessibility improvement made the test's global Rename
locator ambiguous with the dialog's Rename button. The test now targets the dialog
explicitly; the operation itself is unchanged.

## Measured performance and tradeoffs

All timings are synthetic-provider browser measurements, not Dropbox/R2 timings.
The focused test alternates before/after for 20 samples with 2,000 items:

| Metric | Before p50 / p95 | After p50 / p95 |
|---|---:|---:|
| Reused-row redraw | 0.8 / 1.3 ms | 0.8 / 1.2 ms |
| Cold usable list (broader fixture, six samples) | 98 / 103 ms | 101 / 105 ms |
| Cached folder navigation | 6.8 / 7.7 ms | 8.4 / 9.2 ms |
| Uncached folder (simulated latency) | 54 / 67 ms | 55.4 / 59 ms |
| Selection | 0.3 / 0.3 ms | 0.3 / 0.4 ms |
| Preview Open journey (four samples) | 77 / 77 ms | 77 / 95 ms |
| Preview reopen journey | 27 / 28 ms | 30 / 30 ms |

At 1280 px the rendered buffer contains 80 items instead of 56, reflecting more
visible files. The initial denser implementation rendered 90; reducing buffering
and avoiding redundant serialization improved its overhead. Initial slower runs
are retained in the evidence. Broader median script CPU is 12.55→13.15 ms and JS
heap 3.78→3.95 MB. These modest costs are reported, not labelled a speedup.
The focused scroll sample is 16.6/17.7 ms per frame (approximately 60 FPS).
More visible images can produce more thumbnail requests; concurrency stays four
and original image transfer policy is unchanged. Exact saved-JPG selection takes
118 ms in the synthetic paginated fixture. Small-sample p95 is an observed tail,
not a production guarantee. No overall speed improvement is claimed.

## Screenshots and release

Visual comparisons, full-width matrix and raw metrics are in
`files-compact-v6-evidence/`:

- [Before, 1280 px](files-compact-v6-evidence/before-1280.png)
- [After, 1280 px](files-compact-v6-evidence/after-1280.png)
- [After, 375 px](files-compact-v6-evidence/after-375.png)
- [Selection and normal small folder](files-compact-v6-evidence/selection-1280.png)
- [Touch viewport, DPR 3](files-compact-v6-evidence/touch-375-dpr3.png)

Ready for isolated review. No push or deployment. Main has concurrent legitimate
Auto Editions changes at `813ac3fc`; reconcile and retest the combined revision
before a release. Existing V6 real-provider/R2 verification blockers remain.
Nothing in Auto Editions generation, allocations, mappings, archived originals,
Design/Developer Studio, Photoshop host, Shopify or Prodigi was changed.
