# VA PSD permissions — local validation

Verified workspace: `C:/Dev/SportsCaveWorktrees/sports-cave-integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d`.
Branch: `codex/task/integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d`.
Studio task: `20261012-5849050d`; owner: `codex-psd-01a12ffa`.
The category entry point was clean. This existing owned isolated PSD task retains its unfinished cross-browser reliability changes. The separate premium Files task was not edited.

## Cause and permissions

The picker/options/attach routes and mapping store previously required an administrator for every attachment. A VA with Files permission therefore received a server-side denial regardless of platform. The earlier reliability changes in this task replace raw page-entry JSON with friendly HTML errors; there is no evidence that a Mac-specific cookie workaround is needed. Actual Mac account/session equivalence still requires real-device validation.

`attach_missing_psd` is an explicit, opt-in capability stored through the existing account page-permission infrastructure. It requires an active account and Files access. Administrator account-management controls can grant it; no accounts receive it automatically. Ordinary PSD viewing/opening/preview/download remain governed by Files access.

To grant locally after release approval: Settings → Users & Access → edit the selected VA → Page Access → enable Files and Attach Missing PSD (and Edition Ops/Orders page access as required) → Save account. No production permission has been changed.

Picker/options and attach endpoints enforce the capability. Replacement remains administrator-only, including same-file assignments, forged replacement flags and a mapping created after the picker opened. The mapping store checks under the existing transaction/table lock. Immutable file identity, approved folder validation, duplicate prevention, mismatch confirmation, audit insertion, CSRF/origin protection and authenticated sessions remain intact. No schema, migration, reimport, polling or background scan was added.

## Files changed for this permission fix

- `os_accounts.py`: capability, grant validation and existing permission whitelist.
- `app.py`: account permission checkbox.
- `files_upload_api.py`: first-attachment permission gates and administrator-only replacement.
- `psd_mapping_store.py`: locked first-attachment/replacement enforcement.
- `components/psd_picker/picker.html`: permission-aware replacement control and friendly guidance.
- `tests/test_psd_va_permissions.py`, `tests/test_psd_access.py`, `tests/test_psd_picker_api.py`, `tests/test_psd_role_ui.cjs`: focused regression coverage.
- This report. Prior unfinished modal/authentication changes remain listed separately in `PSD_ACCESS_RELIABILITY_LOCAL.md`.

## Validation

122 focused Python tests passed in 7.342 seconds:
`tests.test_psd_access tests.test_psd_va_permissions tests.test_psd_picker_api tests.test_psd_open tests.test_psd_universal tests.test_psd_directory tests.test_files_upload_api tests.test_orders_compact tests.test_edition_ops_table_editing tests.test_desktop_helper tests.test_psd_native_windows`.

Chromium role/cookie/picker tests: 11 scenarios passed (administrator, explicitly authorised VA, ordinary VA and unauthorised account, desktop/mobile viewports). Existing manual picker workflow passed: Add/search/select/mismatch confirmation/save/Open, replacement confirmation and cancellation. Compact modal/Files tests: 9 scenarios passed, including both table launchers, five actions, exact ID across pages, denied/missing/similar IDs, focus restoration/close without reload and existing native Open.

The Windows helper compiled and its hash/Photoshop launch specifications passed without opening a master or launching Photoshop. Synthetic 282-match plus 2,820-row projection benchmark: 0.0195 seconds; 100-order preparation rounded to 0.000 seconds. These are local synthetic measurements, not production network timings. No per-row cloud calls were added.

Broader `tests.test_os_accounts`: 79 tests run; 3 failures also reproduced on unchanged HEAD source, unrelated to this capability:
- `test_accounts_access_exposes_password_access_permission_ticks`
- `test_admin_can_access_every_registered_page_except_owner_only_reporting`
- `test_product_upload_prompt_edit_buttons_follow_account_permission`

WebKit is unavailable locally; no browser/software was installed. User-agent and Chromium mobile fixtures establish device-independent permission behavior, not physical Windows/Mac/iOS/Android compatibility. Real Safari and mobile account/session smoke tests remain required before release. The real signed-cookie verifier and mocked database/Dropbox/native operations were exercised; no production writes or live metadata calls were used.

## Local status

Focused checks pass; ready for local release review with the baseline account-test and real-device limitations above. Studio status remains Tested because changes are deliberately uncommitted. All 282 existing mappings and 51 missing records remain untouched. No commits, pushes, merges, deployments, installations, production permissions or master-file changes occurred. Production activation requires separate owner approval and normal review of the retained task changes; no database migration/backfill is required.
