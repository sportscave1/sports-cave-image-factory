# Largest approved print master — local implementation

Prodigi recommends preparing artwork for the largest offered size and letting its Print API downscale for smaller sizes: https://www.prodigi.com/faq/images/ . Product Details supplies recommended `horizontalResolution` / `verticalResolution` per print area and variant: https://www.prodigi.com/print-api/docs/reference/#product-details . The same reference documents default centre cropping (`fillPrintArea`), aspect-preserving fit (`fitPrintArea`) and stretching (`stretchToPrintArea`). Sports Cave must explicitly validate its layout rather than rely on those defaults.

The registry now records this workflow guidance separately from SKU verification. All 16 existing SKU mappings and storefront references are unchanged. No authorised Prodigi API client/key was found in the configured workspace/tools. Consequently no SKU-specific pixels, bleed, margins or colour requirements were invented or marked verified.

## One asset per unit

`master_plan()` selects the mapped XL SKU for the unit's frame family. Its approved pixels are the master requirement. Smaller requested sizes do not choose independent generators. The master key binds the original order/line/unit, original variant identity, product, assigned number/total, Dropbox ID/revision/content hash and XL specification. It never uses a product's next number. Other units or editions cannot share this numbered image.

The existing owner-run processor accepts `--supplier-master`. Example (currently blocked by missing supplier requirements):

```powershell
python scripts/local_print_test.py --proof output/sc3284_psd_test/verified-export-proof.json --product gid://shopify/Product/10465710768435 --size L --supplier-master --owner codex-psd-inspection-v1-20261013
```

Although that unit was ordered in L, this mode selects XL once. It consumes the retained exact Supabase unit proof and the existing verified Photoshop text-replacement proof, then uses the same bounded processor/cache/lock/retry path. It checks valid/enforced allocation evidence, exact mapped file/revision/hash, original variant, approved source layout, protected number bounds and native pixel proof before processing. The original PSD never changes. A current authenticated production allocation/source check is still required in a future companion job; a retained local proof is not fresh live authorisation.

The exporter continues to use Preserve Details 2.0, preserves the source colour profile and reopens the final JPG. Supplier-master mode exports only the numbered AFTER JPG; BEFORE/AFTER lossless PNGs remain local comparison evidence, not extra print assets. It rejects mismatched source geometry/profile and forbids canvas padding. Existing explicitly labelled storefront tests remain available for historical regression work; they are never promoted to reusable supplier masters. No new JPG was needed for this change: successful Large/XL proofs were reused as evidence.

## Sharing checks

For each XL/L/M/S target, the planner requires:

- Verified recommended pixels, complete supplier canvas dimensions, bleed, safe margins and colour profile.
- Exact proportional supplier pixel and physical canvases. No inferred crop/rotation/aspect tolerance.
- Target pixel dimensions no greater than the XL master.
- An approved artwork layout with matching native dimensions and protected bounds covering the badge and all essential artwork.
- Those normalised protected bounds inside the intersection of XL and target bleed/safe-margin limits.
- Matching colour requirements.

Insets are `[left, top, right, bottom]`; `printable_mm` is the full required canvas including its declared bleed. `protected_bounds` is `[left, top, right, bottom]` in the approved source's pixel coordinates. Do not populate it from a guessed badge position: obtain explicit template/artwork layout approval. Integer source resizing may round to a pixel; supplier-size ratio differences are rejected until a separate layout is approved.

Compatible targets return `Shared master` and `fitPrintArea` as the future submission hint; the same local path/hash is used, with no smaller image generation. Incompatible targets return `Separate layout` with a reason. Unknown requirements return `Unverified`, not an unsupported compatibility claim. Download rechecks current target compatibility and the master dimensions alongside existing owner/identity/hash/approval guards.

## Current real results

| Frame | XL / L / M / S mapped SKUs | Approved sharing |
|---|---|---|
| Black | GLOBAL-CFP-A1 / A2 / A3 / A4 | None verified |
| Oak | GLOBAL-CFP-A1 / A2 / A3 / A4 | None verified |
| White | GLOBAL-CFP-A1 / A2 / A3 / A4 | None verified |
| Unframed | GLOBAL-FAP-A1 / A2 / A3 / A4 | None verified |

SKU names and nominal paper descriptions do not establish printable pixels or bleed compatibility. The existing Large/XL storefront test canvases have different ratios and explicit unapproved test padding. They remain `Review`, `print_ready=false`; the new ratio checks reject promoting those proofs to supplier-master geometry.

Synthetic approved proportional fixtures demonstrate XL/L/M/S reusing one identity. Changed ratios, insufficient pixels, colour differences, unsafe bleed/margins, missing/ambiguous specifications, stale file identity and invalid unit numbers are rejected. These are algorithm tests, not verified Prodigi SKU specifications.

## Remaining activation gates

Obtain authorised Product Details for the exact mapped SKU/variant/print area/destination, and approved supplier template geometry/bleed/margins/colour. Store the verified evidence in the existing registry; recommended pixels alone do not verify layout requirements. Approve each artwork's protected layout and physical print quality. Then connect the fixed-schema authenticated print-job capability through the existing companion and test an actual eligible unit end to end. In-app Generate/Download remains disabled until those gates pass. Open PSD and the compact Orders table remain intact.

No Prodigi uploads/orders, database writes, master edits, mappings changes, new downloads/scans, commits, pushes or deployments.
