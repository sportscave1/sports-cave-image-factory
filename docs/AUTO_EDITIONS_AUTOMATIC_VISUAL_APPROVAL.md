# Automatic visual approval — local implementation and catalogue review

16 October 2026. INTEGRATIONS task `20261016-079c9f85`, owner `codex-auto-visual-20261016-01`. This task uses verified live V18 revision `5c9755441a3a7fafea6c150e5f359173e432d22a` (deployment `dep-db8nl79srm7s739rltlg`). V18 landed separately during development; its incoming files were checked and its overlapping Worker Health/import changes merged with the local edits. Evidence and the pre-integration backup are in `output/automatic-visual/`. No commit, push, deployment, production configuration/approval/data write, companion update or asset upload was performed by this task.

## Existing gates and the change

V16 already validates mapped source identity, geometry, plaque/number roles, installed fonts, all patch hashes, embedded ICC profiles, cloud IDs/revisions/byte counts/content hashes and encoded supplier output. Its automatic production route requires an exact previously human-approved artwork and supplier standard. The configured production standards list is empty. V17 already reuses exact preparation approvals and verified cloud packages. These mechanisms are retained.

The new visual route reuses the V16 asset validator, adds independent trusted-reference and Shopify checks, and writes a distinct `automatic_visual_assessment` audit plus an explicitly automatic layout approval. It never calls the human approval endpoint or sets `visual_approved=true`. The existing `Cloud Ready` database state remains the compatibility contract; Worker Health labels its provenance **Auto Approved**. Supplier-pending cases show **Needs Review**, with the separate visual decision in existing details. Failed evidence checks include a safe stage/reason and audit trace. No layout redesign, new service, dependency or schema migration was introduced.

Approval requires all of the following:

- An owner-approved server policy binding the exact preparation hash, mapped PSD ID/revision/Dropbox content hash, output geometry/ICC, original composite hash and independent first/last-number reference hashes. Every numbered patch is bound by the complete preparation fingerprint and is revalidated against current stored bytes.
- Fresh original PSD metadata matching the pinned source and checkpoint. The existing source-preservation proofs link the PSD preparation to its original lossless composite; the validator recomputes unchanged pixels outside the authorised number region and exact numbered compositions against the approved PNG references. No PSD is reopened, modified or regenerated.
- Fresh cloud receipts and full asset checks, including byte lengths, SHA256, Dropbox hashes and embedded ICC. Existing colour-policy evidence must remain current; a revoked or changed colour policy cannot be overridden by visual approval.
- An exact Shopify product/media identity, product revision and owner-reviewed mockup hash. Reviewed quadrilateral coordinates and a corresponding reference crop account for frames, cropping and perspective, using [Pillow's quadrilateral transform](https://pillow.readthedocs.io/en/stable/reference/ImageTransform.html#PIL.ImageTransform.QuadTransform). The bounded image comparison can veto an ambiguous match; similarity cannot grant identity or approval. Missing registration, tiny visible coverage, changed images or uncertain relationships require review. The existing authenticated Shopify product read is reused.
- Final source/Shopify checks and transaction fences for the product total, mapping, preparation, replacement state, layouts and policy. Concurrent human decisions are retained. Changed sources/preparations and conflicting masters cannot inherit approval.

Certificates expire after 24 hours and are invalid immediately when their exact policy is revoked or changed. Generation checks the full current manifest and source identity again. A currently valid exact-hash certificate avoids another owner review. Rechecks reuse stored preparations and receipts; they never regenerate or reupload artwork. A failed recheck invalidates only that exact automatic eligibility while retaining its layout and append-only history.

## Catalogue result

The read-only authoritative snapshot contained **51 prepared Blocked designs**, plus **16 Cloud Ready designs**; it did not contain 52 currently waiting designs. The earlier set of 52 identities was not supplied, so no claim is made about which design changed state.

The local audit of the 51 current waiting preparations found:

| Result | Designs | Action |
|---|---:|---|
| Stored mapping, preparation, proof and receipt structure passes; no approved trusted-reference policy | 49 | Retain for owner reference review |
| Older cloud receipts omit required byte lengths | 2 | Verify existing cloud assets and reference authority; retain for review |
| Automatically approved by this task | 0 | No live approval writes authorised or performed |

The two older receipt cases are “Hang On To The Roof: Don Mattingly Wall Art” and “Mattingly, Jeter & Judge — The Captains”. Missing receipt lengths are insufficient verification evidence, not proof of corrupt PSDs. The snapshot audit does not claim fresh cloud/pixel comparisons for unapproved candidates: expensive provider work is deliberately not admitted without a trusted owner reference policy. Full decisions and checks are retained in `output/automatic-visual/catalogue-review.json`; the reusable offline command is:

```powershell
python scripts/audit_auto_editions_visual.py --snapshot output/automatic-visual/catalogue-snapshot.json --output output/automatic-visual/catalogue-review.json
```

## Local configuration and remaining release requirements

`AUTO_EDITIONS_VISUAL_AUTO_APPROVAL_ENABLED` is **off by default**. `data/auto_editions_visual_policies.json` is deliberately empty. The prior sRGB template/legacy approvals establish colour assignment authority; they do not establish visual reference or supplier approval.

An approved policy record needs `policy`, `id`, `actor_id`, `approved_at`, `owner_approved`, `download_scope=TEST_ONLY`, `reference_approval_evidence`, exact `source` and `preparation_hash`, output dimensions/ICC, immutable original/numbered-reference file IDs/revisions/SHA256, and the reviewed Shopify media relationship/registration. The synthetic fixture in `tests/test_auto_editions_visual.py` documents the complete shape; it is never installed as a real owner policy. A new source/revision without this authority remains an exception rather than inheriting another artwork's aesthetics. Broad future-template visual authority has not been assumed from a colour policy.

After separate review and release authorisation, approved policies can be populated and the feature enabled. The existing discovery worker processes one due retained preparation per cycle, respecting Pause and durable due state. New imports run the same checks immediately after their durable upload/checkpoint, reusing local imported files with independently checked cloud receipts. A provider failure preserves the successful import for later reconciliation and cannot monopolise the queue.

Automatic **Cloud Ready** authorises only the existing TEST download scope. Print-ready production output still requires V16's exact supplier certificate and variant scope; fulfilment and supplier submission are never authorised by this feature. Original PSDs, mappings, masters, edition numbers, certificates and allocation records are unchanged.

## Validation

Focused synthetic coverage includes exact and false artwork matches, framed/perspective references, changed Shopify products/images, all-patch integrity, original pixels, ICC conflicts and colour-policy revocation, missing/expired/revoked visual policies, concurrent source/mapping/edition-limit/human decisions, failed providers, retained preparations, automatic TEST download eligibility, disabled rollout and post-upload reconciliation without a second transfer. A later exact human approval retains precedence over an earlier uncertain automatic assessment.

The combined Auto Editions/ICC/V16/V17/V18/Worker Health/recovery run passed **271 tests in 138.56 seconds**, with the expected duplicate-ZIP fixture warning. The subsequent targeted approval/quality/eligibility/Worker Health run passed **114 tests in 66.62 seconds**; the final visual suite passed **48 tests in 21.68 seconds** after the listing-fence refinement. Seven JavaScript suites passed, including the new desktop/mobile visual-provenance fixture and the existing Worker Health, V18 races, ICC JSX, V17, quality and onboarding suites. Original-file checks, exact hashes, allocation preservation and no-second-upload assertions pass. Evidence logs are under `output/automatic-visual/`.

Implementation files: `auto_editions_visual.py`, `auto_editions_visual_store.py` and the empty policy JSON; shared `auto_editions_quality.py`; import/discovery hooks; `auto_editions.py`/`auto_editions_status.py` eligibility fences; Worker Health diagnostics and the existing HTML details; the offline audit script and Python/browser tests. One inherited trailing blank line in the V18 SQL benchmark was removed to satisfy Studio's whitespace check; its code is unchanged. No production schema or supplier standard changed. Listings use compact source/dimension/total/colour fields and stored certificates instead of selecting every patch hash or making provider calls.
