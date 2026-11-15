# Sports Cave Files Desktop Helper for macOS

This helper registers `sports-cave-files://` for the current macOS user and stores
only the approved local Dropbox root. It does not store Dropbox credentials.

## Install

1. Extract the ZIP.
2. Control-click `Install.command`, choose Open, and approve it if macOS asks.
3. Select the locally synced `Sportscave Team Folder`.
4. Reopen the browser.

PSD and PSB prefer Adobe Photoshop, AI prefers Adobe Illustrator, and other safe
files use their macOS default application. Paths are restricted to the configured
Dropbox root and executable or script formats are rejected.

Run `Uninstall.command` to remove the helper and its saved root.
