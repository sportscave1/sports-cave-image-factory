# Email inbox lazy-loading release preflight — 20 October 2026

User authorization: deploy the reviewed email updates to Git/Render. Integration
base: `c256c385ac17986023fcf99f641c22be0abb3565` (the current production/main
revision at preflight). Release Studio task: `20261020-7985d737`; owner
`codex-email-release-01a157b1-20261020`.

This release contains the reviewed email patch only. The existing first visible
message opens automatically; other bodies require expansion. Collapsed rows omit
HTML, quoted content, image data and attachment content. Strict cache limits,
inline retry, late-completion guards, exact compose source and refresh/history
selection are covered by focused regressions. Existing released connection
backoff, sanitization and sender-layout fixes are preserved.

Preflight passed: 240 Python tests (232 passed; eight disposable PostgreSQL checks
skipped), seven Node component scripts, actual Chromium synthetic interaction
checks and eight cold/warm network cases. Python syntax, JavaScript syntax,
`git diff --check` and `python scripts/validate_render_topology.py` passed.
`render.yaml`, migrations, dependencies and service identities are unchanged.
There is no Blueprint sync or infrastructure creation in this release.

The loopback fixture uses the real component/controller with fabricated mail,
mocked IMAP/SMTP/storage and a read/compose-only action allowlist. No customer
email was sent or live mailbox data changed during preflight.

For the synthetic 12-message case, the release loads one initial body and one
iframe. Including the deferred header-history response, cold opening transfers
169,811 uncompressed JSON response bytes across two model requests. Warm reopening
transfers 84,906 bytes in one request with no extra provider body read. At 1 Mbps /
150 ms CDP throttling, settling measured about 3.12 seconds cold and 1.24 seconds
warm. Timing includes the existing header-history delay and a 350 ms stabilization
interval. These are synthetic measurements, not production transport timings.

`after.json`, `interactions.json` and `reader.png` capture this release preflight.
Live verification is recorded in Studio/external release evidence after the exact
committed revision is pushed and Render reports it live. Customer inbox content
is not opened for release verification because that could change read state.

Focused Python modules: `test_support_email_performance`,
`test_email_inbox_reliability`, `test_email_loading_performance`,
`test_email_v2b_privacy`, `test_email_send_ux`, `test_email_v2d`,
`test_email_lazy_conversation`, `test_support_email_v2`,
`test_support_email_render`, `test_email_sent_lifecycle`,
`test_email_trash_delete`, `test_email_role_parity`, `test_email_v2a_storage`,
`test_email_full_conversation`, `test_email_dial_backoff`,
`test_email_reply_prompts` (run with `python -m unittest tests.<module> ...`).
