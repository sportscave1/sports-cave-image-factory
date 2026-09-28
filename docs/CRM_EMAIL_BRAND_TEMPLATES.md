# Campaign HTML fidelity and reusable brand sections

Implemented locally on 28 September 2026. No commit, push, deployment, production
database change, real email, or marketing activation was performed.

## Rendering diagnosis and fix

The canonical campaign sanitizer was dropping `bgcolor`, the legacy `font` tag
and its face/color/size attributes, and several legitimate inline presentation
properties. Separately, the durable image validator accepted JPEG/PNG only;
the supplied Shopify `.webp` URL lost its `src` before reaching the preview.
The iframe was not the cause: a permitted Shopify image loads there normally.

`crm_campaign_html.py` now retains safe table/presentation attributes, legacy
font styling, backgrounds, text colours, padding, margins, borders, dimensions,
letter spacing, text transform and approved display values. Existing supported
table structure, links and inline email styles remain available. Safe new-window
links receive `noopener noreferrer`.

Scripts, objects, embeds, user iframes, event handlers, executable/data URLs,
CSS expressions, CSS URL loads/imports and unapproved attributes remain blocked.
This is an inline email-style allowlist; arbitrary head stylesheets, custom CSS
imports and all browser CSS are not supported.

The supplied Shopify logo is requested with `format=png` while preserving its
version query. The public endpoint returned HTTP 200, `image/png`, a PNG byte
signature, and a 950 x 167 image in the browser. Original source remains unchanged.
Durable HTTPS PNG/JPEG URLs remain unchanged. This compatibility conversion is
limited to HTTPS `cdn.shopify.com` WebP URLs and does not relax the shared Flow
asset policy or accept temporary/signed asset URLs.

The exact user-provided header fixture was verified in the actual Campaign iframe:
charcoal RGB 17/17/17, white RGB 255/255/255, and gold RGB 201/163/63, including
the gold separator. Both Desktop and Mobile show the same styling.

## One rendering path

Header, Body and Footer source each pass through the same balanced sanitizer.
The canonical `render_campaign` output appends the protected system footer and
generates plain text. Campaign preview and internal test sending use that same
function; a mocked delivery regression compares the complete outgoing HTML with
the preview renderer output. No test email was actually sent.

## Header/Footer storage and workflow

- Existing `crm_templates` stores both section types, distinguished by
  `content.format = campaign_brand_section_v1` and `content.section`.
- Source HTML and creation/actor metadata live in its existing JSON content;
  existing row timestamps and version columns are reused.
- `crm_template_versions` records create/edit/delete versions.
- `crm_workspace_settings.email_brand_defaults` selects one Header and one Footer;
  `crm_settings_history` records default changes.
- No schema migration or second storage system was added. Page load performs
  reads only. Built-in defaults are virtual and need no seeding write.
- The initial Header uses the existing charcoal/text-or-approved-logo brand
  implementation with its gold accent. The initial Footer uses the existing
  protected system-footer token. No speculative asset, address or link was added.
- New compose state copies the current defaults and leaves Body blank. Save draft
  persists Header/Footer HTML snapshots in the existing campaign document and
  revision model. Later template edits/default changes/deletion do not change
  those saved snapshots. An already-open unsaved compose session also retains
  its selected source until the user explicitly chooses another template.
- Header and Footer accordions offer a selector plus a small Save as template
  popover. Saving a section never replaces Body.
- Campaign Settings > Email brand templates provides default selection and a
  plain shared HTML editor/preview. Shared overwrite requires confirmation and
  a matching version. Existing template permissions permit creation; shared
  overwrite, default changes and deletion require an administrator.
- Active custom names are unique per section, case-insensitively, to avoid
  ambiguous selection. Built-in choices have a stable identifying label.
- Delete custom template requires confirmation and uses logical archival, keeping
  audit/version records. Built-ins and current defaults cannot be deleted.
- General/Flow template selectors exclude these new section records. Existing
  full-template functionality remains unchanged.

## Footer protection and compatibility

`{{SYSTEM_FOOTER}}` is restored when missing from a saved Footer template. More
importantly, the mandatory footer is always rendered outside user-controlled
balanced fragments, so deleting, duplicating, nesting or hiding the token cannot
remove or hide the system identity, configured postal/contact information,
marketing disclosure or unsubscribe information. Configured privacy/social links
continue to use the existing implementation.

No production unsubscribe URL is fabricated. Existing test-only unsubscribe
wording and live-delivery preflight blocks remain. Missing postal information is
still flagged. Required compliance details come from the existing safe settings.

Existing full-HTML campaigns stay on their original rendering path. Defaults are
not retroactively wrapped around saved campaigns, and no stored draft is migrated
or rewritten by page load. Source HTML is retained; only rendered output is
sanitized. No destructive HTML-to-block conversion was introduced.

## Verification

All tests ran locally with mocked delivery. SQL tests used the repository's
disposable loopback PGlite/PostgreSQL fixture, not production Supabase.

| Suite | Result |
| --- | --- |
| `test_crm*.py` (rendering, templates, storage, sections, consent, sending safeguards, Flows) | 164 passed |
| `test_email*.py` | 107 passed |
| `test_support_email*.py` | 212 passed |
| Startup scope, navigation performance, sidebar cleanup/theme, Analytics and Social navigation | 61 passed |
| Python compilation of all nine changed Python files | Passed |
| `git diff --check` | Passed |

Total: 544 tests passed. Tests use `unittest`; pytest is not installed in the
project environment. Existing Streamlit deprecation/bare-mode warnings remain.

Browser checks used the real local app shell and Campaign implementation with
fabricated Shopify/account data, disposable SQL, and outbound application HTTP
blocked. Verified section saves, Make default, default selections in Settings,
footer rendering, the Shopify image, and Desktop/Mobile layouts at 1920 x 1080,
1440 x 900 and 1366 x 768. These are browser layout previews, not Gmail/Outlook
client certification. Existing 600/430/390/375/320 rendering support/tests remain.

Screenshots are local ignored verification artifacts:

- `.venv/brand-1920.jpg`
- `.venv/brand-1440.jpg`
- `.venv/brand-1366.jpg`
- `.venv/brand-mobile.jpg`

## Files changed

- `crm_campaign_html.py`: email presentation allowlist and Shopify PNG resolution.
- `crm_brand_templates.py`: section storage/defaults, permissions and version safety.
- `crm_brand_template_ui.py`: compact section controls and shared-template settings.
- `crm_campaign_page.py`: new compose defaults.
- `crm_html_workspace.py`: section selectors/save controls.
- `crm_settings_page.py`: existing Settings entry for brand templates.
- `crm_store.py`, `crm_workspace_store.py`: isolate section records from existing
  full-template operations while reusing existing persistence.
- `tests/test_crm_brand_templates.py`,
  `tests/fixtures/campaign_header_fidelity.html`: focused regression coverage.
- This report.

## Local testing readiness

Nathan can safely test authoring, section template saves/default changes, draft
save/reload, and previews locally with the intended existing CRM database
configuration. Global template writes are explicit actions, so use a development
database for experimentation. No new migration is required.

`CRM_MARKETING_ENABLED` was not changed; marketing remains OFF. Existing admin,
single internal recipient, allowlist, review, confirmation and duplicate-send
safeguards remain. Inbox, navigation, audience rules and automation behaviour
were not redesigned or altered. No customer or internal test email was sent.
