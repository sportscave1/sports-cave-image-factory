# PSD and Files access reliability — local review

Verified clean retained INTEGRATIONS task worktree before editing:
C:/Dev/SportsCaveWorktrees/sports-cave-integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d.
Branch codex/task/integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d;
task 20261012-5849050d; owner codex-psd-01a12ffa; starting HEAD
97f2cf98ebecb74f386d012478d1e922b53a8b92. Category entry point was not edited.

## Confirmed cause and evidence limits

The reported Administrator access required / upload_error payload originates in
_psd_admin. The Add link opens GET /files-psd-picker. That HTML document route
incorrectly used the JSON API error renderer after permission denial. The same
admin guard also protects picker options and attachment writes. Normal Open PSD,
preview, download and Files browsing never require this administrator guard.

Previously authorised read-only Render logs in Nathan's workspace, on the existing
sports-cave-os service, confirm GET /files-psd-picker 403 at 2026-10-12 23:06:48,
23:07:19 and 23:31:45 UTC (duplicated access entries). Other picker requests returned
200. Only route/method/status/timestamp were retained; no raw paths, product IDs,
user/customer data or credentials copied. Logs contain no account/browser identity.

The exact message occurs after _request_user already accepts a signed account with
Files access. Missing/expired cookies or missing Files permission produce a different
access_denied response. A VA with Files permission reproduces the administrator
attachment denial. Therefore the JSON rendering bug and admin guard are confirmed;
a Safari cookie defect or the Mac using the same administrator identity as Windows
is not confirmed. The Mac's actual current account/role/session still needs checking.

## Fixes and preserved security

Picker and Files HTML entry failures now render compact escaped friendly pages
with Retry, Close and Escape. APIs remain structured JSON consumed safely by clients.
Picker has safe loading/empty/error/retry states, disabled controls before data,
explicit same-origin credentials, responsive sizing and Escape. Already-assigned
files cannot be saved in the UI; server unique assignments, stable ID/location checks,
mismatch/replacement confirmation and audit transactions are unchanged.

Files cookie subject and session version now match the existing Streamlit account
revocation policy. Active admins and authorised VAs with Files permission can read
all five actions. Only admins with Files access can add/replace mappings. Existing
Files deletion capability checks remain unchanged. Unapproved, inactive, missing,
expired or revoked sessions fail closed before Dropbox operations. Safe diagnostics
identify controlled denial reasons without logging cookies, credentials or identities.

Both systems use the same cookie/signing configuration and account store. Existing
Path=/, SameSite=Lax and HTTPS Secure cookie behavior is retained; same-origin
modal/iframe/fetch requests reuse cookies without forwarding session tokens in URLs
or granting privileges. No cross-origin security relaxation.

Embedded Dropbox navigation now offers an explicit Continue in Dropbox link: the
provider's account sign-in opens in its own tab rather than inside a third-party
iframe. This necessary provider handoff leaves Sports Cave OS visible; standalone
PSD navigation remains compatible. In-modal original downloads use the existing
iframe target so download errors remain inside the popup. Existing authenticated,
revision-pinned large-file streaming and Photoshop/helper actions are unchanged.

Open from Files continues to select by immutable ID across folder pages, never
similar filenames; normal browser browsing does not require a helper. Windows/Mac
helper source is untouched. Closing/retrying does not reload background table data.

## Files changed

- files_upload_api.py
- components/psd_picker/picker.html
- components/psd_picker/index.html
- components/psd_open/index.html
- tests/test_psd_access.py (new signed-cookie/ASGI tests)
- tests/test_psd_role_ui.cjs (new cookie/role/picker/provider scenarios)
- tests/test_psd_picker_ui.cjs and tests/test_psd_modal_files_ui.cjs (WebKit runner option)
- docs/PSD_ACCESS_RELIABILITY_LOCAL.md

## Validation

113 focused Python tests passed, including real route dispatch, signed-cookie
validation, role/session checks, Files permissions, mapping conflict/review exclusions,
Edition Ops/Orders, and actual compiled Windows helper verification. External
account/Dropbox/mapping data is mocked; no real mapping writes or PSDs opened.
Admin and VA read requests tested across Windows, Mac Safari/Chrome, iOS/iPadOS,
Android and Linux/ChromeOS user agents; this verifies server policy independence,
not physical browser compatibility. Restricted writes, missing/expired/revoked
sessions and cross-origin attempts denied before external operations.

39 Chromium fixture scenarios passed: 9 new role/cookie/provider/retry/empty cases,
9 existing modal/Files cases, 10 desktop cases and 11 universal cases. Existing
Add/Search/Select/Confirm/Save/replace/cancel workflow also passed. Tests check actual
browser cookie forwarding, exact ID selection, mobile overflow, focus/close/no reload,
optional native opening and friendly denials. No polling or per-row Dropbox reads.

WebKit launch was explicitly attempted; the existing Playwright dependency has no
WebKit executable installed. No browser/software was installed. The role, picker
and modal runners accept PSD_BROWSER=webkit when a runtime is separately available.
WebKit/Safari execution is unverified. Real Windows Edge/Chrome, Mac Safari/Chrome,
iPhone/iPad, Android and native Dropbox operations remain device smoke-test work;
Chromium mocks are not presented as proof of physical-device compatibility.

## Local readiness

Ready for code/release review with WebKit and real-device limitations above.
All 282 mappings, 51 missing records, editions, allocations, orders, certificates,
Shopify data and Dropbox masters are untouched. No migration/import/backfill,
commit/push/deploy, installation or production mutation. No production credentials
used in local testing. Activation requires separately approved code release only;
no database steps. Confirm the owner's Mac uses the current administrator session
on the exact same app origin before its real-device attachment smoke test.
