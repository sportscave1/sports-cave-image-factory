# Author-owned campaign footer

The previous `prepare_footer` restored missing business, address, contact,
website, disclosure and unsubscribe placeholders. It ran during editing,
template handling, draft saving and rendering. Consequently even a completely
custom footer acquired wording the author had not entered.

That restoration is removed. Sectioned campaigns render **Header + Body +
Footer**, using the same canonical output for preview and internal test sending.
No additional footer, paragraph, link, company name or disclosure is injected.
The existing HTML sanitizer still removes unsafe markup and preserves supported
email presentation. Header and Body behaviour is unchanged.

## Source and templates

Footer HTML is saved exactly, including whitespace and `{{UNSUBSCRIBE_URL}}`.
Selecting, editing, saving, making a template default, deletion safeguards and
campaign snapshots use the existing storage and permissions. Nothing rewrites a
footer when it is selected or saved. No schema change is needed.

The existing built-in **Sports Cave Default Footer** remains an editable starting
template; any of its wording or fields can be removed. Optional identity/contact/
address/disclosure placeholders in an authored or older template still resolve
when explicitly present. Missing placeholders are never added. Missing configured
values do not produce customer-facing diagnostic text.

## Unsubscribe validation

Only future live readiness requires a visible, nonempty anchor whose `href` is
`{{UNSUBSCRIBE_URL}}`. The check inspects sanitized markup, so a token in a
comment, script, hidden region or ordinary text does not count. If absent, the
live preflight reports:

> Footer must contain {{UNSUBSCRIBE_URL}} before live marketing can be sent.

The check never changes the design. Drafts and internal previews/tests may omit
this link. Existing HTML safety, admin, allowlist, single-recipient, confirmation,
review and idempotency restrictions still apply to tests.

In internal previews/tests an authored unsubscribe anchor becomes inactive text
in place, retaining its label and supported styling. No fake production URL is
created. When a future caller supplies a recipient-specific unsubscribe URL to
the shared renderer, it must be HTTPS and the footer must already contain the
valid anchor. Only that token is substituted; no second link is added and no
tracking parameters are inserted. This change does not implement/activate live
delivery or a new signing/provider path. All existing production gates remain.

## Compatibility

Legacy `{{SYSTEM_FOOTER}}` markers resolve to nothing at render time. Surrounding
authored HTML stays visible; a marker-only section remains empty. No replacement
footer is fabricated. Stored drafts, templates and historical versions retain
their original strings until the author explicitly edits them. Pre-existing
plain HTML from earlier automatic restoration is also left editable rather than
heuristically deleting content that might belong to the author.

Legacy non-sectioned block/full-document rendering and Flow behaviour are not
changed by this correction. Normal Email Inbox and delivery transport are
untouched. `CRM_MARKETING_ENABLED` remains OFF; no emails, production database
writes, commits, pushes or deployments are performed.

## Verification

Regression coverage includes exact custom source/output, no injected wording,
legacy token handling, live-only unsubscribe rejection, unchanged Header/Body,
template selection/defaults/snapshots, editor reruns, save/reload, and identical
preview/mocked-test HTML. Persistence tests use the disposable loopback
PostgreSQL fixture, never production Supabase.

Results: **176 CRM + 107 Email + 212 support-email tests passed (495 total)**.
All nine changed Python files compiled and `git diff --check` passed. Streamlit
AppTest exercised the real section editor, template choices and save/rerun paths.
Delivery was mocked; no real email was sent. CRM ran on Python 3.12.8 and Email
regressions on the existing Python 3.14 environment.

Files changed:

- `crm_campaign_footer.py`: remove restoration; check live unsubscribe; preserve author styling.
- `crm_campaign_sections.py`: remove the internal-test footer-content requirement.
- `crm_campaign_content.py`: report missing unsubscribe in future-live preflight.
- `crm_brand_templates.py`, `crm_campaign_store.py`: save/load source unchanged.
- `crm_html_workspace.py`: editable source with a live-readiness note, no rewriting callback.
- `tests/test_crm_single_footer.py`, `tests/test_crm_campaign_sections.py`,
  `tests/test_crm_brand_templates.py`: focused and persistence/UI regressions.
- `docs/CRM_SINGLE_FOOTER.md`, `docs/CRM_EMAIL_BRAND_TEMPLATES.md`,
  `docs/CRM_CAMPAIGN_LAYOUT_REFINEMENT.md`: updated behaviour and verification.

Ready for Nathan to test local footer editing, templates and preview/save/reload.
Production activation and delivery remain outside this change.
