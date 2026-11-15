# Global campaign email defaults

Campaigns now use two persistent singleton settings:

- `crm_workspace_settings.key = email_default_header`
- `crm_workspace_settings.key = email_default_footer`

The existing primary key prevents duplicates. Updates use optimistic versions;
concurrent stale edits fail rather than overwrite. Every initialization/update
adds an entry to `crm_settings_history`. An internal rollback uses the prior
history HTML with the current version through `save_email_default`, so validation
and audit remain active. Normal UI has no history/version selector.

## Initial source and adoption

On first access, a transaction locks the existing `email_brand_defaults` registry.
It copies the exact `content.html` of each selected, active `crm_templates` record.
If that section has no selected custom default, it copies the existing built-in
source from `crm_campaign_sections.section_defaults`: the existing header and
`crm_campaign_footer.DEFAULT_FOOTER`. No HTML is redesigned, sanitized in storage,
or replaced by an older template. A missing referenced record fails closed.

Existing brand template records and their versions remain untouched for audit;
the old creation/default-selection/deletion entry points reject new writes.
The new initialization only inserts missing settings, never overwrites one.
No schema migration or production migration command is required. This adoption
was exercised only in the disposable local SQL fixture, not the production DB.
Read-only verification of the documented production CRM project confirmed
`email_brand_defaults` version 5 selects:

- Header: `80ebf8b0-7e6d-4baf-a9a6-f6c1ac2270dc`, **Sports Cave Header**, version 1.
- Footer: `2e793fdc-6217-427c-bbbe-66621a0bfd27`, **Sports Cave Footer default**, version 1.

Both records are active. The header uses the existing Shopify logo, charcoal table
and gold separator. The footer includes the existing three social icons,
shop/contact/privacy links, business/disclosure placeholders and unsubscribe
anchor. Their full stored HTML was read to verify the source; production was not
modified. Adoption selects these records, not the older built-in fallback.

## UI and rendering

Templates > Email defaults has Default Header and Default Footer, each with an
admin-only Edit action. The dialog contains HTML, Cancel, and Save default.
The composer retains fixed Header/Footer rows but no selectors or per-campaign
editors. New drafts store body/middle sections; older draft source is retained
without destructive rewrites. Body-template behavior is unchanged.

`CampaignStore.render_settings` resolves the defaults; the pure renderer uses a
copy of the document with those sections. Preview independently checks default
revisions, so it sees a changed default on the next render. Safe HTML sources are
cached by database identity and revision, bounded to 16 entries. Unchanged reads
fetch only two small key/version records; saves immediately clear the cache.
No subscriber, product, or Shopify API calls are involved.

Preview and Send Test use the configured safe test unsubscribe route. Production
uses the existing recipient token generator. Footer saves require a visible
`{{UNSUBSCRIBE_URL}}` anchor; the existing sanitizer and production validation
remain active. Existing business/contact/privacy placeholders are preserved.

The existing queue freezes `render_settings` (including both sources) when the
send is prepared. Queued/scheduled/sent snapshots therefore remain immutable.
Later edits apply to drafts and future send preparations, not existing jobs.
No new delivery architecture or unsubscribe backend was introduced.

## Local validation

`tests/test_crm_email_defaults.py` covers active-source adoption, singleton count,
exact HTML, edits, reload, revision conflicts, permissions, safe HTML, protected
unsubscribe, cache invalidation, mocked test payload, immutable stored delivery
snapshots, and Streamlit editor interactions. Prior variant-selector tests were
replaced with these intentional singleton behaviors; renderer fidelity tests
remain. No real mail, Shopify writes, or production database writes are used.

Validation result: 283 CRM tests passed, including nine singleton-default tests;
143 Email tests passed with one skipped. All 14 affected Python files compiled;
`git diff --check` passed. Streamlit AppTest verified the composer and edit dialog;
no manual live-browser or live-send test was performed. Marketing configuration
remains unchanged/off; nothing was committed, pushed or deployed.
