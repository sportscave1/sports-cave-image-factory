# Windows recorder packaging

Development candidate only. Building a ZIP does not authorize installing,
publishing, deploying or replacing an installed helper.

From the assigned task worktree on Windows:

```powershell
& windows-screen-recorder/native/build.ps1
python -B scripts/build_task_recorder_package.py --output C:\path\to\candidate\SportsCaveTaskRecorder.zip
```

The ZIP contains the browser helper, desktop adapter, x64 native executable,
native build sources, pinned dependency closure and setup scripts. Its manifest
records every file's size and SHA-256. ZIP ordering/timestamps are fixed, so the
same source bytes and native executable produce identical archives. Native
compilation is a separate Windows build step; this does not claim identical PE
bytes across compiler versions. No recordings, profile, settings, credentials,
receipts or recovery archives are packaged.

For a future authorized hosted release, build and review the archive on Windows,
place that exact artifact on the host and set
`SPORTS_CAVE_RECORDER_WINDOWS_PACKAGE` to its absolute path. The authenticated
setup route validates it before serving. A local Windows source checkout can
build the download from its compiled candidate. A host without either artifact
returns an explicit unavailable response rather than a partial browser package.
No Render service or environment setting has been changed by this work.

Setup requires an existing Python 3.11+ bootstrap. It prepares a dedicated
environment and pinned dependencies in a new version directory, then checks
package integrity, imports and isolated adapter initialization before switching
`active.txt`. First setup needs network access for Python packages and the pinned
Playwright browser. Preparation failure or a busy recorder leaves the active
version selected. The stable Start launcher also preserves the existing Windows
startup entry, and supports a previous legacy installation during migration.

Version directories live under `%LOCALAPPDATA%\SportsCaveOS\TaskRecorderHelper`.
New release directories use a 20-character key to leave room for deeply nested
Playwright files under the Windows path limit. Integrity still uses the complete
SHA-256 manifest digest; existing 64-character release directories remain readable.
Recorder data stays in the separate `TaskRecorderV1` directory. `Rollback.cmd`
selects the retained previous release after confirming the helper is idle; it
does not restore/delete recordings, journals, settings or profile data. A failed
post-start capability check attempts rollback when a previous installation exists.

Current validation includes a fresh disposable environment with the real pinned
dependencies and browser, plus actual helper startup, update selection and
rollback in disposable storage. The generated PowerShell Rollback entrypoint
also selected a compact previous release using a real disposable environment;
its final helper launch was intercepted for that entrypoint check. Both Start
and Rollback accept current compact and retained older release IDs.
Installed first setup, startup, update and
rollback acceptance remain required before a release. Do not treat these checks
as installed-helper evidence.
