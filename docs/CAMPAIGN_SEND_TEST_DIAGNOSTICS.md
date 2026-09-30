# Send test diagnostics — local implementation, 30 September 2026

## Verified production content (read-only)

Campaign **Peter Brock Tribute — 20 Years Remembered**, version 48, contains:

| Section | Source | ALT | Result |
|---|---|---|---|
| HTML Section 2 | `ICON_URL_CERTIFICATE` | empty | URL and description required |
| HTML Section 2 | `ICON_URL_FRAME` | empty | URL and description required |
| HTML Section 2 | `ICON_URL_FINISH` | empty | URL and description required |
| HTML Section 2 | `ICON_URL_DELIVERY` | empty | URL and description required |

Diagnostic section ID: `661173abb85e42228b05c2997dce431b`.
These are four nonblank, relative placeholder strings, not Shopify, SVG or WebP URLs.
The sanitizer correctly drops their invalid source attributes from outgoing HTML;
the stored source still contains the placeholders. Each also has `alt=""`, hence
the previous eight repeated failures.

A read-only equality comparison confirmed this section exactly matches the saved
**Trust Icons template version 2** HTML. It is editable template-derived body
content, not the locked Header or Footer or a current built-in template. The
section's template reference names version 3, but its copied HTML remains version
2. This establishes the stale copied content, not who pasted or changed it.
Version 3 uses real Shopify WebP icon URLs but still has empty ALT values; versions
4 and 5 have no image tags. No live template or campaign was modified.

Catalogue `e23b65cb9f17476eaa91600bd4b678f5` is explicitly **visible with zero
products** in the current document and saved versions 46–48. Its blocker is
correct. There is no evidence that the current error is a hidden section being
validated or a sanitizer changing its visibility.

The draft requires real image URLs and meaningful ALT text, or replacement/removal
of that old trust-icon content, plus adding products or hiding Catalogue. No URL
was invented. Shopify WebP conversion is not the cause of these four failures;
the existing `format=png` conversion was verified through the rendering tests.

## Implementation

- Structured diagnostics retain section ID/type, friendly display label, issue
  type/count, safe asset references and message. Four images with two faults each
  appear as four affected images, not eight repeated section errors.
- Expected preflight and stale-catalogue errors carry structured checks rather
  than a huge concatenated exception. Unexpected service failures remain errors.
- The native Send test popover is capped at 520px with compact spacing, a recipient
  row, grouped section issues and collapsed technical details. Raw IDs are only
  in technical details/navigation attributes, not visible section labels.
- Go to section closes the popover, selects Editor, expands the existing section,
  scrolls to it and focuses its heading. It reuses local section state and does
  not emit a save, recreate the draft or discard pending HTML.
- Opening refreshes readiness within the existing fragment. Submission retains
  the existing acknowledgement barrier for pending section edits and recovery
  state, then reads the current editor before authoritative validation.
- Empty Image sections and hidden sections remain ignored; visible empty
  catalogues, unsafe images, missing meaningful ALT and stale facts remain blocked.
- No image policy, consent/suppression rule, transport or locked content changed.

## Files changed

Production: `crm_campaign_issues.py`, `crm_campaign_test_ui.py`,
`crm_campaign_content.py`, `crm_campaign_send_ui.py`, `crm_campaign_send.py`,
`crm_campaign_store.py`, `crm_campaign_page.py`, `crm_catalogue.py`,
`components/campaign_recovery/test_sections.js`,
`components/crm_sections/composer.js`.

Tests: `tests/test_crm_test_issue_groups.py`,
`tests/test_crm_test_preflight_issues.py`, `tests/test_crm_test_sections.cjs`,
`tests/fixtures/crm_test_preflight_preview.py`. This report is also new.

## Validation

- Focused campaign/send/image/catalogue/review/recovery/section suite: 103 passed.
- Final issue suite including real Streamlit AppTest expected-error submission:
  5 passed (four overlap the focused run; the modal regression is additional).
- JavaScript section/flush/image/review/navigation suites: 7 passed.
- Full CRM run: 448 tests; 446 passed, 1 skipped, 1 existing failure in
  `test_manifest_is_reviewed_and_check_never_connects`. It assumes CRM migrations
  are the final deployment manifest entries, whereas later Email migrations
  follow them. Unrelated deployment files were not changed.
- Changed Python compilation, JavaScript syntax and `git diff --check` passed.
- Offline real Streamlit editor fixture checked at 1366×768, 1440×900,
  1920×1080 and 900×768. Compact grouped errors, no horizontal popup overflow,
  correct section navigation, correction to ready state, Escape/outside dismissal
  and Escape focus return were checked. No browser console errors observed.
- Fixture delivery is replaced with validation only. This is not a production
  end-to-end delivery test. Production data was inspected only through SELECTs.

No email sent, campaign published, Shopify/customer data changed, commit, push or
deployment. The local code is ready for review; the existing live draft still
needs the genuine content corrections described above before it can pass.
