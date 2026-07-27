# Sports Cave OS Desktop

Sports Cave OS Desktop is the persistent Windows host for genuine outbound file
dragging, Windows file Copy and image clipboard actions. It displays the existing
Sports Cave OS in WebView2 and runs only for the current Windows user.

## Install

1. Extract the helper package.
2. Double-click `Install.cmd`.
3. Open **Sports Cave OS Desktop** from the Start menu.
4. Sign in normally if the existing Sports Cave session is not already present.

The desktop app does not contain Dropbox credentials. Sports Cave OS validates
each selected Dropbox identity and revision, then issues a short-lived transfer
grant. Validated items already present in the configured local Dropbox Team
Folder are exposed directly. Missing local items fall back to the bounded
`%LOCALAPPDATA%\SportsCaveOS\FileCache`. Both paths use genuine
`FileDrop`/`CF_HDROP` data.

The installer starts a windowless per-user host, creates a Start menu shortcut
and registers the existing Open protocols. Normal use does not launch PowerShell
or a Command Prompt window. Native bridge messages are accepted only from
configured Sports Cave OS origins and use an allowlisted action set.

Copy places materialised files or folders on the persistent Windows file
clipboard with a Copy effect. Cut remains the existing internal Sports Cave
Files move workflow.

Dragging begins inside the persistent desktop process and uses native
`DragDrop.DoDragDrop` with a Copy effect. Receiving applications get real local
files, not browser blobs, URLs or path text. Multiple files, folders and Unicode
names are supported.

Run `Install.cmd` again to upgrade an existing installation. The installer
replaces the desktop host, refreshes current-user protocol registration and
starts the new version. No administrator access is normally required.

Minimal diagnostics are written to
`%LOCALAPPDATA%\SportsCaveOS\Logs\desktop.log`. The log records only the
action, outcome, error code and item count; it does not record paths, signed URLs
or credentials.

## Uninstall

Run `%LOCALAPPDATA%\SportsCaveFilesHelper\Uninstall.ps1` with PowerShell.
