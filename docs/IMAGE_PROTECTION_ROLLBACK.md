# Image Protection rollback — local implementation

No commit, push, deployment, Render/environment changes, Shopify writes, production
SQL writes, table drops, or down migrations were performed for this request.

## Outcome

Restored the lightweight existing login/cookie system and signed utility tokens.
Stay signed in remains 30 days. Removed durable-session/SID/reauth checks, idle
locks, privacy overlays, app watermark, OS protection middleware, Windows capture
exclusion, Files audit/session hooks and image export conversion hooks.

One compatibility endpoint clears previously issued HttpOnly cookies before the
original browser cookie writer runs. It is same-origin POST-only, invoked only
on explicit login/logout, and has no authentication/session/database/provider
work. This avoids trapping existing browsers behind an unreplaceable cookie.
Plain local Streamlit's missing API router (404) retains the original cookie path.

The new Settings → Image Protection entry uses existing admin permissions. It
loads ten harmless website flags from the existing app_settings table only on
that page or a storefront config request. Public configuration has a bounded
60-second process cache (including failures), plus 30-second HTTP caching.
No new database schema, provider calls, or normal-navigation policy reads.

Storefront deters artwork context menus, dragging, selection/copy, WebKit callout,
printing and targeted Save shortcuts. Watermark defaults OFF. No OS or account/
checkout execution, no polling, no global text/form context-menu blocking, no
pointer/touch/swipe/cart changes. Browser and OS screenshot limits remain explicit.

## Mixed hunks removed, valid work preserved

- app.py: only OS protection changes reversed; added a lazy Image Protection route.
- os_accounts.py: reverted security guards/session bumps; replaced the obsolete
  route with the existing-permission admin-only image settings child.
- Top-bar HTML: removed security action; added Image Protection in Settings only
  when the existing allowed-navigation map grants it. top_bar.py itself unchanged.
- sports_cave_server.py: removed security session routes and ProtectionHeaders;
  retained Wall Preview analytics, CRM, Google SEO and all other routes.
- run_migrations.py: removed only the OS protection migration from active startup
  deployment manifest. Historical SQL and reviewed SHA entry unchanged. Wall
  Preview analytics and CRM migrations/checksums preserved.
- supabase_backend.py: removed only two sensitive_admin hook pairs from manual
  certificate entry points. Existing identity checks, database administrator
  enforcement, allocations, counters and audit logic remain untouched. These
  hooks already existed in the specified parent, so a parent restore alone would
  incorrectly leave a dependency on the deleted module.
- wall_preview_analytics_api.py: replaced only the removed session-store dependency
  with existing signed cookie/account active/version/page-permission validation.
  No analytics/event/query/purchase logic changes.

Wall Preview completion, storage recovery, inbox/analytics implementation, Social
Media, CRM worker, Google OAuth core and the historical SQL are unchanged from
current HEAD. Subsequent commits are preserved; no entire commit was reverted.

## Remaining reference audit

No active durable-security module imports, SID handling, OS protection script,
lock screen or native capture affinity remain. Old implementation/inventory docs
are historical only. The migration SQL and reviewed hash remain as history.

SPORTS_CAVE_AUTH_SECRET remains an OPTIONAL legacy cookie/top-bar signing salt in
app.py, files_upload_api.py, google_seo_api.py and top_bar_security.py, exactly as
in the requested parent baseline. The analytics read adapter uses the same cookie
contract. Removing this optional input would invalidate existing signed cookies
and disagree with the requested restoration of that baseline. All missing-secret
startup guards are removed; tests prove Render-mode login and utility requests
work when absent. Its production value was not inspected or changed. Test
references exercise an empty value; none are a deployment requirement.

## Validation

- 79 account/auth tests passed independently.
- Top bar: 20 passed, 1 pre-existing source-text assertion failed.
- Startup/lazy: 9 passed; extra new navigation test covers Dashboard/Orders/Email/Files.
- Files: 40 passed. Certificate suites: 32 passed. Mockup/export: 19 passed.
- Google SEO: 32 passed. Planner: 48 passed, 2 pre-existing source-text assertions failed.
- Image Protection: 11 passed (UI test uses a fresh Streamlit runtime).
- Wall Preview: 165 passed using the disposable local database/mocked providers.
- Total selected Python tests: 455 passed / 458; 3 baseline failures below.
- Storefront browser fixture: 120 checks across 1920/1366/750/390/320 widths passed;
  tests include Render outage, normal text/forms, cart/variant/carousel controls,
  touch event pass-through, explicit artwork, disabled state, watermark and OS exclusion.
- Existing top-bar browser navigation tests passed.
- Browser HttpOnly-to-normal cookie transition, 30-day persistence and logout passed.
- Server import with socket connections blocked passed (56 routes).
- py_compile of every changed Python source passed; deployment manifest check READY;
  git diff --check passed.

Known baseline failures (reproduced against 72fea360 source, left unchanged):
1. test_top_bar: expects absent resetInitialSidebarScroll.
2. test_daily_planner_overhaul: expects absent schedulePlannerStatus(30000).
3. test_daily_planner_plan_tomorrow: expects outdated Save today's plan label expression.

Combined bare-mode Streamlit tests leak process-global form context into AppTest;
running existing suites independently avoids this test-harness interference. No
application change was made to hide the issue. Physical iOS/Android long-press and
an actual live Shopify theme were not tested or changed; touch-callout is best-effort.

## Exact files restored to parent bytes

- `.env.example`
- `sc_auth.py`
- `top_bar_api.py`
- `top_bar_security.py`
- `daily_planner.py`
- `files_upload_api.py`
- `google_seo_api.py`
- `desktop_helper/SportsCaveFilesDesktop.cs`
- `image_factory.py`
- `tests/test_files_upload_api.py`
- `tests/test_os_accounts.py`
- `tests/test_manual_certificate_controls.py`
- `tests/test_manual_certificate_persistence.py`
- `tests/test_mockup_eight_image_manifest.py`

## Additional modified files (selective hooks, storefront or documentation)

- `SHOPIFY_INSTALLATION.md`
- `app.py`
- `components/sports_cave_top_bar/index.html`
- `docs/SECURITY_PROTECTION_IMPLEMENTATION.md`
- `os_accounts.py`
- `run_migrations.py`
- `sports_cave_server.py`
- `storefront-protection.js`
- `storefront_protection_api.py`
- `supabase_backend.py`
- `tests/test_storefront_protection.cjs`
- `wall_preview_analytics_api.py`

## Deleted security-only files

- `app-protection.js`
- `protected_web_images.py`
- `protection_headers.py`
- `scripts/test_native_security_build.ps1`
- `security_protection.py`
- `security_protection_ui.py`
- `security_session_api.py`
- `tests/fixtures/security_settings.py`
- `tests/security_postgres_server.mjs`
- `tests/test_app_protection.cjs`
- `tests/test_security_protection.py`
- `tests/test_security_protection_sql.py`
- `tests/test_security_settings_ui.cjs`

## New isolated feature/test/report files

- `auth_cookie_cleanup.py`
- `tests/test_auth_cookie_transition.cjs`
- `image_protection.py`
- `image_protection_ui.py`
- `tests/test_image_protection.py`
- `docs/IMAGE_PROTECTION_ROLLBACK.md`

## Retained storefront installation

`storefront-protection.js`, `storefront_protection_api.py`, `shopify-storefront-protection.liquid` (unchanged include), `SHOPIFY_INSTALLATION.md`.
