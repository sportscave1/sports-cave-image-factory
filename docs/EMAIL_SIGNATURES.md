# Sports Cave email signatures — local implementation report

27 September 2026. Local changes only; no commit, push, deployment, real email,
mailbox operation, or infrastructure/configuration change was performed.

## Implementation

1. **Official asset:** the app header uses `assets/sports-cave-os-app-icon.webp`.
   Signatures reuse its existing installed-app derivative,
   `static/branding/sports-cave-os-icon-192-v2.png` (192 × 192 RGBA, 21,084 bytes).
   The official gold SC monogram is displayed at 56 × 56. Neither asset was changed.
2. **Image delivery:** outgoing HTML references
   `cid:sports-cave-signature-logo@sportscaveshop.com`. The MIME builder includes
   that PNG once, with matching Content-ID and inline disposition. Browser previews
   receive an in-memory data URI; settings storage converts this back to the CID.
   There is no public image fetch, filesystem URL, or logo binary in Supabase.
3. **Nathan:** Kind regards; Nathan Baker; Founder; Sports Cave; mailbox and website;
   the requested collector tagline. A 520px maximum table, 56px logo, 2px gold
   divider, 17px bold name, 12px role/contacts and 10px muted tagline keep it compact.
4. **Maria:** the same layout, with Maria / Customer Support. Both signatures use
   `mailto:hello@sportscaveshop.com` and `https://www.sportscaveshop.com`.
5. **Default mapping:** Nathan explicitly approved role defaults after account IDs
   were unavailable: active identified OS admin → Nathan; active identified OS
   worker/staff → Maria. A saved per-user signature preference takes precedence.
   This deliberately applies to all admins/staff, not only two guessed accounts.
6. **Internal account:** Reina's OS user ID, username, display name, permissions and
   account records are unchanged. The existing database preference key `reina` is
   retained for compatibility; no schema migration is required.
7. **Customer-facing identity:** the `reina` signature profile is labelled Maria,
   uses Maria in both bodies, and has public profile ID `maria`. New managed draft
   headers also use `maria`. Outgoing signatures contain no OS account ID.
8. **Company Default:** remains selectable and is the fallback for unidentified,
   inactive or unsupported-role users. Custom existing Company Default text is
   preserved. The old generic company template upgrades to the branded default.
9. **Selection:** New Mail, Reply, Reply All and Forward all use the role default
   or saved user preference. The compose dropdown offers Nathan, Maria, Company
   Default and No signature. Settings exposes all three previews to staff and
   admins, existing Save my preference, and admin-only signature editing.
10. **One active signature:** editable body, signature key and quote remain separate.
    Switching replaces the preview. Compose protects the signature from accidental
    editing. Managed MIME markers and draft-only version/signature/mode headers
    restore that separation on reopen. Repeated saves/reopens regenerate one
    signature and one logo, above quoted history. Exact legacy OS-generated
    signatures are recognised and upgraded. Unrecognised/external draft sign-offs
    are not guessed: those drafts retain No signature until explicitly changed.
11. **Plain text:** both requested fallbacks are included with real paragraph/line
    breaks, the correct name/role, contact details and title-case tagline. No CID
    or HTML markup appears in the plain alternative.
12. **MIME:** `multipart/alternative` contains `text/plain` and
    `multipart/related(text/html, image/png)`. Normal file attachments add the
    existing outer `multipart/mixed`. Bcc, reply headers, attachment limits,
    message identity and SMTP send/reconciliation behavior are preserved.
13. **Client compatibility:** conservative tables, inline styles, system Arial,
    explicit image dimensions and a transparent PNG avoid flex/grid, external
    styles or large background blocks. Signature HTML uses a restricted sanitizer;
    the general message sanitizer remains unchanged. The preview CSP permits
    inline style attributes and data images, while continuing to block remote
    images and connections. Actual Gmail, Outlook, Apple Mail, Yahoo, Thunderbird
    and dark-mode delivery have not been tested because real sends were prohibited.

## Files

14. Added:
    - `support_email_signatures.py` — official asset and branded profiles.
    - `tests/test_support_email_signatures.py` — signature/MIME/storage/role coverage.
    - `docs/EMAIL_SIGNATURES.md` — this report.

    Updated:
    - `support_email_compose.py` — safe signature HTML, role defaults, MIME and draft separation.
    - `support_email_store.py` — normalize existing signature settings and strip preview data URIs.
    - `support_email_workspace.py` — reuse signature model cache and provide one preview logo.
    - `components/support_email/index.html` — signature preview CSP.
    - `components/support_email/mail.js` — protected compose preview and settings previews.
    - `components/support_email/style.css` — compact signature spacing and responsive table.
    - `tests/test_support_email_v2.py` — updated managed-draft roundtrip assertion.
    - `tests/fixtures/email_desktop_preview.py` — existing untracked local harness;
      added `?account=staff` to preview the existing Reina fixture identity.

    Pre-existing edits in `docs/EMAIL_V1.md` and `tests/email_v2_fixtures.py` were
    left intact and are not signature changes. No logo asset, account/auth module,
    schema, Render configuration or unrelated product module was changed.

## Validation

15. Python suites (run separately with `python -m unittest ... -q`):

    | Suite | Result |
    | --- | --- |
    | `tests.test_support_email` | 45 passed |
    | `tests.test_support_email_v2` | 57 passed |
    | `tests.test_support_email_performance` | 22 passed |
    | `tests.test_support_email_signatures` | 22 passed |
    | `tests.test_os_accounts` | 79 passed |
    | `tests.test_navigation_performance` | 23 passed |
    | `tests.test_app_startup_scope_regression` | 6 passed |
    | `tests.test_email_service` | 6 passed |
    | `tests.test_app_favicon` | 1 passed |
    | `tests.test_app_install_branding` | 16 passed, 1 pre-existing failure |

    Total: 277 passed, 1 pre-existing failure across these selected suites.
    The failure is `test_production_server_wraps_streamlit_with_initial_branding`:
    it expects the old one-line wrapper assignment, whereas the server already
    wraps branding in `ConstantTimeHealthMiddleware`. Both test and server files
    were verified identical to HEAD. This unrelated test was not modified.

    Also passed: Python compilation for all seven changed/new Python files;
    `node --check components/support_email/mail.js`;
    `node tests/test_support_email_component.cjs` (20 assertions);
    `git diff --check`; and `scripts/validate_render_topology.py` (read-only).

    The fixture performance probe retained cached reopening without mailbox calls,
    order queries or HTML conversion: 0.02ms open + 0.13ms model preparation in
    this run. These are local Python fixture timings, not production latency.

16. Browser verification uses the existing fabricated mailbox harness on localhost
    with IMAP/SMTP constructors blocked and all store/audit operations mocked.
    Admin New Mail defaulted to Nathan; Reina/staff New Mail defaulted to Maria.
    Company Default replaced Maria rather than appending. The logo loaded from
    local preview bytes, at 56px. Signature tables measured 520px on the 1440 × 1000
    desktop viewport and 378px on the 1230 × 900 narrow viewport, with no signature
    horizontal overflow. Screenshots are in ignored `output/`:
    `EMAIL_SIGNATURE_NATHAN.png`, `EMAIL_SIGNATURE_MARIA.png`,
    `EMAIL_SIGNATURE_MARIA_NARROW.png`, `EMAIL_SIGNATURE_MARIA_REPLY.png`.
    Saving and reopening a fabricated mailbox draft restored one Maria signature
    and one logo. Reply selected Maria and displayed her signature above the
    previous-message block. Staff Settings showed all three read-only previews;
    admin Settings retained editing controls. The fresh staff browser tab reported
    no console errors.

17. No social icons/links, promotional buttons, tracking pixels or analytics URLs
    were added.
18. VentraIP remains authoritative for message bodies, attachments, Sent and drafts.
    Supabase stores only the existing workflow/settings metadata, including
    administrator-authored signature configuration and per-user preference. No new
    customer content writes were added. IMAP, SMTP authentication, cached mailbox
    selection, folders, search, recipients, mail actions, order matching and other
    Sports Cave OS modules retain their existing implementation and tested behavior.
19. Ready for Nathan's review and an approved deployment/test cycle. No migration,
    environment variable or account rename is needed. Before calling recipient
    rendering production-verified, inspect a controlled delivered message in the
    major target mail clients, including dark mode, and confirm the logo remains
    inline alongside a normal attachment. No real-send or deployment approval has
    been used or assumed.

## Repeat local visual checks

Run `.venv/Scripts/python.exe -m streamlit run tests/fixtures/email_desktop_preview.py --server.port 8503`.
Open `http://127.0.0.1:8503/` for admin and `http://127.0.0.1:8503/?account=staff`
for Reina. Open New Mail and each reply/forward mode; switch signature; save and
reopen a fabricated draft; inspect Settings previews. The fixture's normal UI may
say a draft was saved in the real mailbox: its provider is mocked and only writes
to its in-memory fixture. Do not replace this harness with production credentials.
