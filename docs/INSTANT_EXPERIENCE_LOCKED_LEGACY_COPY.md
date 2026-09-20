# Instant Experience text restoration

New Ads Instant Experience text only. No commit, push, deployment or live changes.

## Historical source and active path

The legacy implementation already existed in `ads_page.py` at commit `844a0c5` (2026-08-09). It contained the Legacy Standard short-line structure, the Greatness/framed hook and the Choose-a-Side question/response/ownership structure. Commit `7a883d2` (2026-09-16) restored a historical style helper in `ads_ie_legacy_description.py` for Creative Refresh.

New Ads instead used `ads_ie_copy.instructions` with randomized hook families, optional historical styles and freshness instructions that could replace the recognizable frameworks. Its Choose-a-Side rule also excluded single-subject products. The current user note is the authority for the restored permanent hooks and collector-versus-generic-print challenge, including the Greatness opening for every category.

The existing legacy helper now also exposes `build_new_ad_style_rules`, used by the active `build_ads_prompt` → `build_standard_instant_experience_prompt` → `ads_ie_copy.instructions` path. Its existing Creative Refresh function is unchanged. This is one New Ads template source, not a second competing generator.

## Restored behavior

1. `legacy_standard`: subject/product opening, collector identity, "This isn't wall art.", scarcity and "Secure yours." CTA: Claim Your Edition.
2. `framed_greatness`: always "Greatness doesn't fade.\nIt gets framed.", product/collector meaning, scarcity and "Secure yours." CTA: Secure Your Edition.
3. `choose_a_side`: collector-wall question, product versus forgettable print, "You already know the answer.", scarcity and the two-line collector ownership challenge. CTA: Own This Edition.

Each creative has exactly one Description, Headline and CTA. Personalisation varies supplied subjects, product identity and supporting language inside the fixed framework. NBA uses basketball, NFL football, cricket cricket, and motorsport uses motorsport/racing. Team context supports club identity; unknown categories use sporting/fan language. No invented achievements or rivalry. Recent history can vary supporting lines and headlines, but cannot replace the defining hooks.

Text uses the user-approved 100-edition baseline: "Limited to 100 worldwide." or "Only 100 exist." An explicit separately verified different limit takes precedence. This rule is for descriptions only; it does not change image scarcity wording.

The keys `legacy_standard`, `framed_greatness`, `choose_a_side` remain the writing identities in fixed slot order. Exported CSV headers, output mode, route IDs, variation=1, row count and historical description identity cells remain unchanged. In the existing one-copy CSV format, description_key can remain legacy_standard as a compatibility cell; it does not select the slot's new writing framework.

## Illustrative non-motorsport output: Michael Jordan

The following is a worked example of the three restored frameworks for a Michael Jordan basketball product, using the instructed 100-edition baseline and no specific achievement claims.

### Ad 1 — legacy_standard

Michael Jordan.
Basketball legacy on display.
Court-side intensity on the wall.
Made for basketball collectors.

This isn't wall art.
It's a statement of basketball identity.

Limited to 100 worldwide.
Made for fans who know why it matters.

Secure yours.

**Headline:** Michael Jordan. Your Statement.

**CTA:** Claim Your Edition

### Ad 2 — framed_greatness

Greatness doesn't fade.
It gets framed.

Michael Jordan.
A name that belongs on your basketball wall.

Made for collectors who want their basketball identity on display.

Limited to 100 worldwide.
Built for serious collectors.
Made for fans who know why it matters.

Secure yours.

**Headline:** Frame Your Jordan Legacy

**CTA:** Secure Your Edition

### Ad 3 — choose_a_side

What deserves the centre of your basketball wall?

Something that actually means something.

Michael Jordan
or another forgettable basketball print?

You already know the answer.

Only 100 exist.

Claim this edition for your collection…
or leave it for another collector.

**Headline:** Make Your Wall Jordan's

**CTA:** Own This Edition

## Validation

- 89 targeted tests passed: locked copy, current copy/UI, actual public prompt integration, historical descriptions, visual systems, image/export workflow, winner refinement and Posting handoff.
- 82 Creative Refresh and final-review tests passed.
- 12 additional tests passed: affected Ads prompt assertions plus the locked-copy regressions.
- Changed Python files compile; `git diff --check` passed.
- Byte-for-byte baseline tests prove standalone image prompts for NBA, NFL, cricket and motorsport, and the Creative Refresh prompt, match the start of this task.
- CSV import/export round-trip checks retain three rows and unchanged identity cells and copy bytes.

No image-generation code, camera/room logic, folder-generation code, Posting, Meta Review, Product Uploads, Shopify, Supabase, Orders or Mockups changed in this text-only task. Earlier uncommitted image/export work remains intact.

## Files changed in this task

- `ads_ie_legacy_description.py`
- `ads_ie_copy.py`
- `ads_page.py` (New Ads copy wrapper and copy-fatigue instructions only)
- `tests/test_ads_ie_copy_v2.py`
- `tests/test_ads_ie_locked_legacy_copy.py`
- `tests/test_ads_page.py` (affected copy assertions)
- `tests/fixtures/ie_locked_copy_scope_baseline.json`
- `docs/INSTANT_EXPERIENCE_LOCKED_LEGACY_COPY.md`
