# One editable campaign footer

The duplicate layer came from three places: the brand-template saver appended
`{{SYSTEM_FOOTER}}`, section import stripped that token, and `render_campaign`
always appended a separate beige compliance footer. The editable source and the
protected footer were consequently two independent visual blocks.

Sectioned campaigns now render **Header + Body + Footer** through the same
canonical path used by Preview and the existing internal test sender. That path
does not append the old footer. The legacy block/full-document rendering path
remains unchanged, including Flow behaviour.

The built-in **Sports Cave Default Footer** is editable charcoal/gold table HTML
with the approved Instagram, Facebook and Pinterest links. New campaigns select
it automatically (or the saved global default). Custom templates use the existing
CRM template rows, versions, permissions, default registry and delete safeguards.
No new table, migration, remote write or delivery configuration is introduced.

Required business identity, contact, disclosure, configured business address and
unsubscribe content resolve from inline placeholders inside this same HTML.
Website/contact/privacy links are resolved only from safe configured values.
Unsubscribe URLs are not tracked or invented. During tests, the inactive link is
plain “Unsubscribe” text; the existing live-delivery preflight remains blocked.
An unconfigured postal address produces no customer-facing diagnostic or empty
address paragraph. The existing verified-address requirement for future live
sending remains enforced outside the email design.

If a required placeholder is deleted, small inline elements are restored in the
existing final table cell/container, with a warning in the campaign editor. No
additional styled footer is generated. Sanitized markup must still expose the
required placeholders and a nonempty unsubscribe anchor. Hidden/comment-only or
invalid content fails preflight; invalid shared templates cannot be saved.
Drafts may retain invalid layout work for correction, but cannot be test-sent.
Unsafe scripts, event handlers and protocols stay blocked. The sanitizer's
placeholder exception accepts only four named tokens, never arbitrary URLs.

Legacy `{{SYSTEM_FOOTER}}` sources are converted in memory, removing that token
and adding only missing inline fields. Token-only defaults become the new branded
template. Conversion is idempotent and saved only through the existing explicit
draft/template save. Historical versions are not rewritten. Header/body HTML is
not transformed. Saved campaigns keep their own source snapshots.

Changed files:

- `crm_campaign_footer.py`: default, compatibility, inline protection/rendering.
- `crm_campaign_html.py`: narrowly scoped safe placeholder link handling.
- `crm_campaign_sections.py`, `crm_campaign_content.py`: one-footer assembly.
- `crm_brand_templates.py`, `crm_campaign_store.py`: existing storage integration.
- `crm_html_workspace.py`: editable footer, restoration warning and concise note.
- `tests/test_crm_single_footer.py`, `tests/test_crm_campaign_sections.py`,
  `tests/test_crm_brand_templates.py`: rendering, UI, snapshot and mocked-send coverage.
- `docs/CRM_SINGLE_FOOTER.md`, `docs/CRM_EMAIL_BRAND_TEMPLATES.md`,
  `docs/CRM_CAMPAIGN_LAYOUT_REFINEMENT.md`: current behaviour and compatibility notes.

Verification uses disposable local PostgreSQL and mocked delivery. No emails,
production migrations, commits, pushes or deployments are performed. Marketing
delivery remains off and the normal Email Inbox code is unchanged.

Final checks: 173 CRM tests (including template/rendering/SQL/UI and mocked test
delivery), 107 Email tests, and 212 support-email tests passed. CRM ran under
Python 3.12.8; the final Email runs used the existing Python 3.14 environment.
An earlier Windows 3.12 run hit intermittent unchanged support-email refresh
assertions: fixture loads can receive the same `datetime.now()` refresh timestamp,
so their snapshot version does not advance. Those tests and mailbox code were
not modified in this footer task. Python compilation and Git whitespace checks
also passed. AppTest verified default selection, editing, inline restoration,
preview, save/reload and existing template controls; no live send was performed.
