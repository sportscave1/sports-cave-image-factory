# Sports Cave Files Desktop Helper

This optional Windows helper opens locally synced Dropbox files from Sports Cave OS.
It stores no Dropbox credentials and runs only for the current Windows user.

## Install

1. Extract the helper package.
2. Double-click `Install.cmd`.
3. Select the locally synced `Sportscave Team Folder` when prompted.
4. Restart the browser.

PSD and PSB files prefer Adobe Photoshop, AI files prefer Adobe Illustrator, and
other files use their Windows default application. The helper accepts only safe
relative paths inside the approved folder. Dropbox Desktop must be installed and
signed in. The helper reads the first byte before launch so Dropbox hydrates an
online-only placeholder before the associated application receives it.

The installer registers a Photoshop-specific protocol launcher for PSD and PSB
files so the browser's external-application prompt identifies Photoshop instead
of Windows PowerShell. Both protocol routes use the same root-scoped helper.

Copy and Cut in Sports Cave Files also use the helper to place the selected,
validated local Dropbox files on the Windows file clipboard. This allows Paste
in Windows Explorer or on the Desktop, including multiple files and folders.
Copy uses the Windows copy effect and Cut uses the Windows move effect.

## Uninstall

Run `%LOCALAPPDATA%\SportsCaveFilesHelper\Uninstall.ps1` with PowerShell.
