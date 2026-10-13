# Premium Files explorer — local-only completion

Task 20261012-2be53608 / owner codex-files-premium-20261013.
Verified isolated worktree:
C:/Dev/SportsCaveWorktrees/sports-cave-integrations-premium-files-explorer-ui-and-native-open--20261012-2be53608.
Branch codex/task/integrations-premium-files-explorer-ui-and-native-open--20261012-2be53608;
approved Studio base bdc46c292a9a4213a21b861184c35186820a16be.

The earlier PSD worktree contains unfinished access-reliability changes. Its files,
Git branch and complete uncommitted status were preserved. No reset, stash, clean,
copy of unfinished work or Git merge. Studio's approved base predates the PSD task,
so this is a small isolated delta requiring reviewed integration with that task,
not a standalone replacement release of the older approved base.

## Implemented

Presentation-only Files polish: compact rounded controls, consistent SVG command
icons, subtle hover/press states, clearer selection/focus, soft toolbar surfaces,
professional context menus/dialogs, touch sizing and reduced-motion support.
Existing folder/view/scroll geometry, data loading and file structure retained.

Single-click selects; Ctrl/Meta/Shift selection remains. Double-click opens files
or folders. Enter and toolbar/context Open prefer the native default app for images
where the existing bridge supports it; browser fallback retains the existing image
viewer. The original openItem and all transfer/cache functions remain unchanged.

Open With appears in toolbar and file context menu; Preview and Download are
available alongside it. Preview reuses the existing image viewer and clearly
reports unsupported file types without downloading masters. Existing other context
menu actions remain in place. PSD popup and its five actions were not edited.

Optional Windows openWith capability uses the existing authenticated transfer and
local-first/managed-cache materialisation, then calls SHOpenWithDialog for exactly
one non-executable file. No arbitrary application path or command is accepted.
Native origin checks, transfer validation and blocked types retained. Dialog
cancellation/error is surfaced. Existing openFile, drag/copy, Photoshop and Mac
helper methods remain intact. No chooser, settings page or real application was
launched during tests; only compile/specification checks and bridge mocks.

Remember/change application delegates to OS preferences. Open With chooses an app
for one opening only. On Windows 10/11 SHOpenWithDialog cannot set the remembered
default, per Microsoft; an explicit, capability-gated Open Default Apps action
opens Windows Settings. Subsequent native Open already uses OS file associations.
No registry writes or automatic system association changes. Finder/mobile/Linux
instructions reflect their real OS controls rather than simulated installed-app
lists. No new preference database or parallel application registry.

References:
- https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/ns-shlobj_core-openasinfo
- https://learn.microsoft.com/en-us/windows/apps/develop/launch/launch-default-apps-settings
- https://support.microsoft.com/en-us/windows/apps/change-default-apps-in-windows

## Files changed

- components/files_window/index.html: targeted UI and opening additions.
- desktop_helper/SportsCaveFilesDesktop.cs: optional openWith/appDefaults actions
  and an additive OS chooser class, no changes to caches/helper version/installers.
- tests/test_desktop_helper.py: expanded capability contract expectation.
- tests/test_files_premium_ui.cjs: native/browser, desktop/mobile interactions.
- tests/test_files_premium_perf.cjs: local baseline comparison.
- tests/test_files_premium_preservation.py: unchanged working-code checks.
- tests/test_files_premium_native.py: actual compiled helper/specification checks.
- tests/premium_compat.py and tests/test_files_premium_combined.cjs: temporary
  in-memory composition checks against retained PSD source; not an integration.
- docs/FILES_PREMIUM_LOCAL.md: this report.

## Preservation and validation

104 focused Python tests passed: Dropbox integration, Files APIs/operations,
permissions, helper contracts/build and preservation assertions. Assertions confirm
existing upload/download/rename/delete/copy/move, folder/search/navigation/pagination,
selection helpers, native transfer/cache code, Dropbox backend, Supabase backend,
Mac helper and installer bytes remain unchanged against the approved base.

39 retained PSD tests also passed, including 282 approved matches, 40 review
exclusions, permissions, conflicts and multi-product identity. The 282 mappings,
51 missing records, Shopify/editions/orders/certificates and masters were never
written, imported or migrated. No production credentials or customer data used.

Four premium Chromium native/browser and mobile/desktop scenarios passed, including
single selection without API calls, modifiers, double-click/Enter, ID-bearing native
transfers, OS chooser/defaults, folder navigation and search. Nine existing PSD modal
cases passed using a temporary combined Files fixture. Actual retained v10 helper
compiled with the additive actions; NativePhotoshop/NativeCache/TransferGrant bodies
were checked unchanged. No Git integration or edits to retained source occurred.

Mock 500-row render medians (three runs): baseline 127ms, premium 128ms. Each render
made one metadata folder request; master downloads 0. This is a local fixture
comparison, not production/network timing. No scans, polling or new per-row queries.
A mocked Files screenshot was inspected locally; no production-connected preview.

## Limitations and readiness

Ready for review as an isolated additive delta. Not ready to deploy as a standalone
older-base checkout: reviewed integration with the retained PSD/access task is still
required, then an existing helper package refresh after separate owner approval.
Helper version and installer intentionally unchanged; do not install the isolated
older-base package as a replacement for the current v10 package. Compatibility
was validated against v10 source in temporary fixtures, not by modifying it.

Windows Open With requires the refreshed existing helper advertising openWith;
older helpers retain normal Open and show safe download/Open With guidance.
Remembered preferences use explicit OS settings, not a pretend in-app checkbox.
Mac native app chooser is not exposed by the existing browser bridge; its existing
PSD helper/default-app workflow remains untouched, with Finder guidance for other
choices. Mobile/Linux/ChromeOS use supported preview/download and OS opening/share
controls. Unsupported browser previews remain unsupported.

Real Windows chooser/default settings, Mac/mobile apps, cloud hydration, and device
browser smoke testing remain necessary after an approved combined release. No
software was installed, no system associations changed, and no live master opened.
No commit, push, merge, deployment, schema/env/schedule change or production mutation.
