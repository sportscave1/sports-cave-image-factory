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

## Uninstall

Run `%LOCALAPPDATA%\SportsCaveFilesHelper\Uninstall.ps1` with PowerShell.
