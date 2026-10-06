# Security & Protection implementation — 5 October 2026

## Deployment state

The additive security migration is applied to the production OS database and
recorded in its existing migration ledger. All four new tables have RLS enabled;
neither anon nor authenticated roles can select them. Existing users, preview
records, and business tables were preserved.

Application deployment is pending confirmation that the existing primary Render
service has a non-empty `SPORTS_CAVE_AUTH_SECRET`. Its value must never be sent to
chat or committed. Production refuses the publicly predictable default signing
key. Rotating an existing key would invalidate sessions and is not required.

The canonical service remains `sports-cave-os` / `srv-d8kl4on7f7vs73dvavv0`.
No Render service, Blueprint, plan, or environment value was changed.

## Architecture and access

The application remains Streamlit 1.58 on the existing Starlette server, custom
signed account authentication, PostgreSQL/Supabase, and the existing WPF WebView2
desktop wrapper. The existing account/permission registry is reused. Security &
Protection is an admin-only child route reached through the top-right Settings
cog, never another permanent sidebar item.

The main UI validates the durable session and live account/session version before
executing page actions. Files, native transfer grants, utility APIs/Daily Planner,
and Google setup also recheck backend access. Utility tokens no longer authorize
using stale role/permission snapshots. Security changes, account access changes,
session revocation, private file deletion, and manual certificate overrides require
recent password verification at their backend boundary.

`POST /api/os/security/session` is same-origin and body-bounded. New account login
uses a 90-second, one-use server handoff to set HttpOnly/Secure/SameSite=Lax cookies;
the signed authentication token is not embedded in new browser JavaScript. The
bootstrap compatibility flow is rejected by Files once a real account exists.
Password/access changes rotate the existing account session version. Logout,
revocation, expiry, and idle lock are durable; a revoked token cannot recreate its
session. Password verification expires after five minutes and is rate limited.
Login attempts are bounded per normalized login identifier in durable storage.
MFA/passkeys are truthfully shown as requiring provider configuration.

Idle locking uses one browser deadline and one bounded activity heartbeat, with
server-side inactivity enforcement. The overlay retains the current editor DOM
and unsaved fields. The heartbeat never extends an idle session just because a
tab exists. Focus/visibility privacy and an optional name/time watermark are
deterrence, not operating-system screenshot blocking.

## Storage and images

Masters remain in existing private input/output storage and private Dropbox,
accessible only through the authenticated Files workflow. No new public master
endpoint, public bucket, or public Dropbox sharing link was added. Existing
authenticated temporary downloads remain short-lived capability URLs; already
downloaded native files cannot be revoked remotely.

Shopify and social export staging now generates separate decoded/re-encoded
derivatives, preserving filenames and source masters. Default long edge is
1800px, configurable to 1200/1600/1800/2000/2400; no upscaling. JPEG/WebP quality
is 85. EXIF/GPS is stripped, ICC profiles are retained, writes are atomic. Optional
baked watermarks support corner/centre/repeated and Low/Medium/High opacity.
Never-serve-masters and protected-web-images-only cannot be disabled.

The read-only live Shopify audit covered 424 products and 3,109 images with complete
image pagination. It flagged 647 images across 110 products above the default
1800px limit. Dimensions are a review signal, not proof of master-file exposure.
See `PUBLIC_IMAGE_AUDIT_20261005.csv`. Existing media was not replaced or deleted.
Settings also provides a bounded, manual audit and the reviewed report download.

## Storefront contract

The existing primary hosts `GET /storefront-protection.js` and
`GET/OPTIONS /api/storefront-protection/config` after deployment. Config contains
only the explicit public protection allowlist and accepts the existing www and
non-www storefront origins. Failed config reads use a basic safe deterrence
baseline without blocking shopping. The deferred script has no framework or
polling loop, and added-image processing is debounced and bounded.

Deterrence covers context menus, image dragging, selection/copy, printing,
save/print shortcuts, WebKit touch callouts, and a small copyright notice. Editable
form controls remain usable. Checkout/account paths are exempt. No advertising
events are sent. Shopify installation has not been performed; use the exact line
in `SHOPIFY_INSTALLATION.md` after the endpoints are deployed.

## Native capture and limits

The existing Windows wrapper uses `SetWindowDisplayAffinity(0x11)` only on Windows
build 19041+, then checks `GetWindowDisplayAffinity`. Every wrapper window uses
the same protection. Runtime status is displayed as enabled only when affinity
was verified. The updated package compiles, but its real screenshot/recording,
login, and navigation tests still require running the installed updated wrapper.
It has not been installed or substituted for the user's running desktop app.
Microsoft documents this as capture exclusion, not DRM or a guarantee against
all capture methods: https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity

No Android or iOS native wrapper exists in this repository; those platforms are
reported unavailable. Browser/PWA and Shopify cannot prevent OS screenshots,
developer tools, direct public CDN downloads, or determined copying. No fake MFA
or platform protection status is presented.

## Audit and headers

The private security audit records login success/failure, session creation/expiry/
revocation/logout, lock, reauthentication, protection-setting changes, private
master access, and explicit image audit actions. It accepts no arbitrary payload
metadata or credentials. Existing account/certificate/edition audit records are
read alongside it rather than duplicated with financial payloads. Admin filters
support resource, event, user, date, newest-first and bounded results.

Baseline nosniff/referrer/HSTS headers preserve provider/embed behavior. The
security transport has no-store and a narrow default-src/frame-ancestors CSP.
The main OS document only allows same-origin framing; there is no new global CSP that could break existing editors, camera, or recording.
Constant-time liveness remains independent of storage and provider calls.

## Validation

- 45 focused policy/API/image and real local PostgreSQL tests pass.
- 79 Accounts & Access tests pass; 40 Files API tests pass.
- 49 certificate/edition control regression tests pass.
- 44 desktop/image/product-mode tests pass.
- 292 broader Design Studio/product/Shopify/webhook/Orders/Edition tests ran: 
  258 passed and 34 existing cases were skipped.
- Top-bar suite: 20 pass, one pre-existing source assertion fails because
  `resetInitialSidebarScroll` is absent from the unchanged baseline component.
- 60 storefront browser assertions, 25 Settings assertions at
  1920/1366/750/390/320, and six app privacy/idle/draft assertions pass.
- Python compilation, JavaScript syntax, migration review/idempotency, Render
  topology validation, diff whitespace checks and native compilation pass.
- Shopify connector schema validation passed the read-only image query; the
  optional CLI validator was blocked by automatic review because its required
  prompt argument would disclose internal task context. It was not retried.

No emails, automations, order allocation, Shopify customer writes, or webhook
subscription mutations were performed during this work. Concurrent Automations
changes are excluded from the security deployment path manifest.

Production health currently returns 200. The proposed script/config paths still return
the old HTML app shell, not JavaScript/JSON: they are not deployed yet. No public
master bytes were returned by the tested private-path probe.

## Deployment command

After confirming the existing primary service's signing secret is configured,
one command from the repository root uses the existing guarded Git/Render flow:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& ./scripts/deploy.ps1 -Message 'Add Security and Protection controls' -Paths @(Get-Content ./docs/SECURITY_PROTECTION_DEPLOY_PATHS.txt)"
```

This selects only the reviewed security files. Ordinary push triggers existing
auto-deploy; it does not create services. Verify LIVE, public config/script/CORS,
authenticated login/Settings/Files, and native capture before claiming production
or platform protection complete.
