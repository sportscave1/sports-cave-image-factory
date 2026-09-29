# Campaign template picker and performance pass

Locally verified on 29 September 2026. No production storage, Shopify, mail,
marketing configuration, commits, pushes or deployment were changed.

## Findings and changes

The library already selected metadata rather than every HTML body. Its remaining
cost was an uncached SELECT on every composer/list rerun, a new full-row SELECT on
each Edit/Use (including dialog reruns), and explicit full-app reruns after
Save/Delete/Use. The defaults list also requested both default records just to
draw two labels. Default HTML was already revision-cached for rendering.

The middle tab is now **Editor**. Add section retains Add HTML and Add Catalogue,
followed by alphabetically sorted saved campaign template names. The generic
Add Template step and secondary picker are removed. Names are inserted into the
DOM as text, not markup. Arrow navigation and Escape include the dynamic entries;
long lists scroll inside the compact menu.

Selecting a name loads only that ID/version and uses the existing copy insertion:
fill an empty HTML Section 1, otherwise append the next numbered HTML section.
The copy remains editable and independent of later source edits or deletion.
No campaign schema or rendering semantics changed. Existing template IDs, names,
HTML and version history remain intact.

`crm_template_cache.py` reuses the existing `DisplayCache`: 600-second TTL,
128-entry / 4 MiB bounds, per-database connection namespace, defensive copies,
and serialized misses. Metadata and selected bodies share this process-local
cache; body keys include template ID and version. Successful `save_design`
(create/edit/rename) and `archive_design` invalidate it after the transaction.
Failed writes do not invalidate; failed reads are not cached. Another server
process or an out-of-band database edit is observed on expiry, not via a new
cross-process invalidation service. This cache is for template editing, never
audience eligibility or delivery authorization.

The defaults list now performs no HTML read. Clicking Edit loads that singleton
only. Default selection, version conflict checks and preview revision freshness
are unchanged. Template failures show localized messages and preserve campaign
content and the Add HTML / Add Catalogue actions.

On Streamlit 1.64 (the local Render-equivalent runtime), template callbacks target
the existing composer fragment. They do not rerun Recent Campaigns, workspace
settings, send controls or subscriber calculation. A small isolated adapter uses
Streamlit's native Dialog.close handle because the public decorator does not
expose one; closing occurs during the targeted composer rerun. On the also-supported
Streamlit 1.58 environment, named fragments are unavailable: the normal full-app
dialog close remains as a compatibility fallback. Cache benefits apply there too.
No dependency upgrade was introduced. Recheck the adapter when upgrading Streamlit.

## Measurements

Real local elapsed times against the disposable loopback PGlite/PostgreSQL fixture,
with 12 synthetic 3.5 KB templates, using the same operations before/after. These
are individual server data-path samples, not browser latency or production SLAs.
`tests/profile_campaign_templates.py` reproduces the after profile. SQL statement
counts include BEGIN/COMMIT; SELECT counts below show the actual reads.

| Operation | Before ms | After ms | SELECTs before → after |
|---|---:|---:|---:|
| Cold metadata list | 4.455 | 2.636 | 1 → 1 |
| Repeat metadata list | 17.922 | 0.176 | 1 → 0 |
| First selected Edit body | 4.135 | 3.534 | 1 → 1 |
| Repeat same body | 17.965 | 0.004 | 1 → 0 |
| Use already-loaded body / copy | 2.915 | 0.113 | 1 → 0 |
| Save transaction | 4.202 | 24.141 | 0 → 0 |

Save still has four SQL statements (BEGIN, versioned write, history write, COMMIT).
Its higher sampled time is reported unchanged; no write-speed improvement is
claimed. The improvement after Save is avoiding unnecessary page work on the newer
runtime. Initial library payloads contain zero HTML documents both before and
after. One selected body's first open loads one body; repeat opens load none.
Opening/closing Add section itself is browser-local and makes no request.
No Shopify API requests were added. Exact browser event-to-paint and production
database timings were not measured.

## Validation

- 304 CRM/Campaign/Flow tests passed on the Render-equivalent Python 3.12 /
  Streamlit 1.64 runtime, including ten new picker/cache/lifecycle tests.
- 144 Email tests passed on Python 3.14 / Streamlit 1.58, including navigation
  and the compatibility fallback; no tests skipped in the final run.
- 35 navigation/startup/sidebar tests passed.
- JavaScript section component tests passed, including dynamic names, direct
  selected ID/version, safe text labels and empty-template behavior.
- Python compilation and `git diff --check` passed.
- Local browser: 1440×900 and 1920×1080. Verified Editor label, direct insertion,
  preview update, Templates Use/Edit/Save, Header/Footer Edit/Cancel, creation,
  rename and archive menu updates, preserved inserted copies, and Escape dismissal.
  Used synthetic Trust Icons and temporary templates in disposable storage only.

## Files changed

Application: `crm_campaign_page.py`, `crm_campaign_library.py`,
`crm_section_ui.py`, `crm_template_cache.py`, `crm_workspace_store.py`,
`crm_brand_templates.py`, `crm_brand_template_ui.py`,
`components/crm_sections/composer.js`, `components/crm_sections/index.html`,
`components/crm_sections/style.css`.

Validation: `tests/test_crm_template_picker.py`,
`tests/profile_campaign_templates.py`, `tests/test_crm_sections_component.cjs`,
`tests/test_crm_campaign_sections.py`, `tests/test_crm_campaign_v2.py`,
`tests/test_crm_html_workspace.py`, `tests/test_crm_segment_performance.py`,
`tests/test_email_navigation.py`, and this report.

The tab assertions were updated to Editor; existing consent, native unsubscribe,
catalogue, scheduling, production queue and email rendering tests remain intact.
CRM_MARKETING_ENABLED remains false; no email was sent. Safe for local review.
