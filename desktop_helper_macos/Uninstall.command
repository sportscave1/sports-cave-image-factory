#!/bin/zsh
set -euo pipefail
APP_DIR="$HOME/Applications/Sports Cave Files Helper.app"
SUPPORT_DIR="$HOME/Library/Application Support/SportsCaveFilesHelper"
if [[ -d "$APP_DIR" ]]; then
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -u "$APP_DIR" || true
  /bin/rm -rf "$APP_DIR"
fi
if [[ -d "$SUPPORT_DIR" ]]; then
  /bin/rm -rf "$SUPPORT_DIR"
fi
echo "Sports Cave desktop helper uninstalled."
