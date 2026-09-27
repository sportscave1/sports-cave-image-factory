# Files launcher deployment fix

1. **Root cause established locally:** a process-global cached component can exist
   without registration in the active Streamlit runtime. `declare_component`
   registers only with an active ScriptRunContext. The old wrapper returned its
   cached object forever, including after an early bare-context declaration or
   runtime replacement. The actual Starlette component route then returned
   **404, `Component not found`**. This exact response was reproduced before the
   patch. The first event that populated the deployed cache is not established;
   production logs/runtime were not accessed.
2. **History:** `ce9cc09` introduced the imported wrapper and process-global cache.
   Its predecessor, `160f2ba86ef3ff85c03f3656da035b1327df2241`, kept the declaration
   helper inside the rerun-executed app module. This is the last pre-regression
   code baseline, not a verified last successful production deployment. Later
   wrapper commits changed Orders link helpers, not this cache behavior.
3. **Assets:** not missing, ignored, mispathed or misnamed in the repository.
   `components/files_window_launcher/index.html` is a tracked self-contained
   HTML/JS/CSS asset. No frontend dist/build directory, npm step, package manifest
   or external JS/CSS bundle is required. The relevant files have no ignore match.
4. **Files changed in this task:** `files_window_launcher.py`,
   `tests/test_files_window_launcher.py`,
   `tests/fixtures/files_launcher_preview.py`, and this report. Existing unrelated
   working changes were preserved. No frontend asset was altered or recreated.
5. **Declaration:** before and after:
   `declare_component("files_window_launcher", path=str(COMPONENT_DIR))`.
   Before, it was called only once per process; now it is called at every launcher
   mount. Streamlit idempotently registers the same name and owns registry locking.
   The widget key is unchanged. `files_window_launcher.files_window_launcher` is
   Streamlit's valid `module.name` namespace and must not be renamed to fix this.
6. **Production mode:** absolute source-relative bundled asset path, no localhost
   URL or development server. Render configuration and dependencies unchanged.
7. **Git tracking:** `git ls-files` confirms both the wrapper and frontend entrypoint
   are tracked. Tests verify the local frontend bytes equal `git show HEAD:<path>`.
8. **Clean export:** test exports the frontend exclusively from git to an empty
   temporary directory, overlays only the proposed wrapper patch, and imports /
   validates assets in a fresh Python process. This passes without generated files
   or a build step. It is a component-focused clean export, not a full Render build.
9. **Sidebar:** real component renders between VA Training and Reporting, followed
   by Accounts & Access. Production sidebar order/permission gate were not edited.
10. **Error gone locally:** actual framework route returns 200 after early bare
    declaration, repeated mounts and replacement registries. Browser shows Files
    without the warning or `Component not found`, including after a rerun.
11. **Data untouched:** no file records, Google Drive, Supabase, Dropbox, PSD links,
    product assets or other storage were read or modified by this fix.
12. **Tests:** 103 Files/component/navigation/startup tests passed. Additional
    regression suite: 61 passed, two pre-existing failures in unchanged code:
    `test_custom_upload_routes_run_with_the_streamlit_app` expects the primary
    service command in the intentionally support-only Render Blueprint;
    `test_no_native_streamlit_toast_bypasses_the_three_second_runtime` finds an
    existing native toast in Ads posting. Python compilation, bundled JS syntax
    and `git diff --check` passed. No new test failures.
13. **Browser:** local Streamlit Starlette App uses the real production bundled
    launcher, intentionally predeclared before any session. Files is visible and
    survives reruns. Clicking it requests `/files-window` with HTTP 200. Its local
    destination is a harmless fixture, not real storage. The in-app browser did
    not expose the named popup as a separate controllable tab, so popup content
    was not visually inspected. Screenshot: `output/FILES_LAUNCHER_FIXED.png`.
14. **Isolation:** app/sidebar implementation, server, Render, Email, search,
    notifications and all other business modules unchanged by this task.
15. **Deployment readiness:** ready for an approved controlled deployment smoke
    test. The reproduced registration defect is fixed; confirm the real deployed
    Files launcher after rollout. No commit, push, deploy, Render, database or
    cloud-storage action was performed. Stop for Nathan's approval.
