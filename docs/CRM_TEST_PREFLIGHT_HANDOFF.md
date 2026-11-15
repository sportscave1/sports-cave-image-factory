# Campaign Send test preflight — local handoff

## Findings and limits

The production draft/settings were not available locally (database and Shopify token environment variables are absent). The three generic production failures cannot identify a specific section ID or URL. No claim is made that a particular live asset caused them.

The current canonical pipeline already skips hidden sections, treats empty Image sections as empty, and converts Shopify CDN WebP to `format=png`. Full-pipeline fixtures confirm this. Aggregation is local to one render and deterministic. The default Header has Sports Cave alt text; the default Footer uses text social links. No incompatible default system asset was found; stored production email defaults remain unverified.

Concrete defects fixed:

- Send test could race pending component changes and retain an older fragment editor argument. It now waits for section acknowledgements and browser recovery, then uses the current campaign session object. Click and Enter both use the barrier. Failure prevents submission rather than validating an old snapshot.
- Browser recovery handled HTML edits but ignored Image edits. Both now use the same recovery path.
- Errors lacked section/asset attribution. Failed preflight now reports visible section type/ID, a sanitized image reference and the failed rule, or catalogue product/title and corrective action. Locked Header/Footer sources are identified explicitly. Query strings, credentials and private/data URLs are not echoed.
- The test store path lacked fresh catalogue comparison (old tests explicitly asserted no refresh). New test operations now perform a fresh read-only comparison before recipient lookup, snapshot and transport. Changed/unavailable facts block with a refresh-specific error. Receipt replay happens first and does not refetch or resend.
- Incomplete image tags are rejected as malformed markup rather than being mistaken for harmless empty sections.

Hidden drafts are retained; no renderer exclusion or alt/URL safety gate was removed. Preview and test use the existing canonical renderer. Transport, audience, consent, suppression and idempotency logic are unchanged.

## Files in this pass

- `crm_campaign_issues.py` (new diagnostics)
- `crm_campaign_content.py`, `crm_campaign_html.py`
- `crm_campaign_send.py`, `crm_campaign_send_ui.py`, `crm_campaign_store.py`
- `crm_catalogue.py`
- `components/crm_sections/composer.js`
- `components/campaign_recovery/recovery.js`, `components/campaign_recovery/test_flush.js`
- `tests/test_crm_modular_catalogue.py`
- `tests/test_crm_test_preflight_issues.py`, `tests/test_crm_test_flush.cjs`
- `tests/fixtures/crm_test_preflight_preview.py`
- this handoff

Prior Inbox changes remain separate and uncommitted.

## Validation

- Focused Python: 128 tests, 127 passed, 1 skipped (environment-gated); includes SQL-backed send/persistence, HTML sanitizer, image, catalogue, templates, footer and section tests.
- JavaScript: 5 passed, 0 failed; component, history, image controls and async test submission barrier.
- Full CRM run: 438 tests, 436 passed, 1 skipped, 1 failed. The failure is the existing `test_crm_storage_recovery` assumption that CRM migrations must be the deployment manifest suffix; earlier Inbox changes appended Email migrations. This pass did not alter migration configuration. The final malformed-image regression was added afterward and passed in the focused run.
- Changed Python compilation, JavaScript syntax and `git diff --check` passed.
- Actual offline Streamlit browser fixture at 1440×900 and 1920×1080: show/hide empty catalogue, empty Image, immediate missing-alt and corrected WebP edits, image removal/re-addition, click and Enter submission. Named failures and valid outcomes observed; no browser console errors after final reload. No live send occurred: fixture replaces delivery with validation only.
- Production saved defaults, exact live offending URLs/IDs, and a full authenticated production editor/session remain unverified.

Example error: `Image [section-id] · Missing meaningful ALT text: cdn.shopify.com/…/artwork.webp`.

No email sent, campaign published, Shopify product/customer changed, commit, push or deployment. Live asset identification still requires read-only access to the affected draft and resolved email defaults; do not consider the production incident conclusively diagnosed solely from these fixtures.
