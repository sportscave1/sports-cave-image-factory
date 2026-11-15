#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
SUPPORT_DIR="$HOME/Library/Application Support/SportsCaveFilesHelper"
APP_DIR="$HOME/Applications/Sports Cave Files Helper.app"

ROOT="${1:-}"
if [[ -z "$ROOT" ]]; then
  ROOT="$(/usr/bin/osascript -e 'POSIX path of (choose folder with prompt "Select your locally synced Sportscave Team Folder")')"
fi
ROOT="${ROOT%/}"
if [[ ! -d "$ROOT" ]]; then
  echo "The selected folder does not exist." >&2
  exit 1
fi

/bin/mkdir -p "$SUPPORT_DIR" "$HOME/Applications"
/bin/cp "$SCRIPT_DIR/SportsCaveFilesHelper.py" "$SUPPORT_DIR/SportsCaveFilesHelper.py"
/bin/chmod 700 "$SUPPORT_DIR/SportsCaveFilesHelper.py"
/usr/bin/python3 - "$SUPPORT_DIR/config.json" "$ROOT" <<'PY'
import json
import sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({"RootPath": sys.argv[2]}, ensure_ascii=False), encoding="utf-8")
PY

TMP_SOURCE="$(/usr/bin/mktemp -t sports-cave-files-helper).applescript"
cat > "$TMP_SOURCE" <<APPLESCRIPT
on open location protocolUri
  do shell script "/usr/bin/python3 " & quoted form of "$SUPPORT_DIR/SportsCaveFilesHelper.py" & " " & quoted form of protocolUri
end open location
APPLESCRIPT
/bin/rm -rf "$APP_DIR"
/usr/bin/osacompile -o "$APP_DIR" "$TMP_SOURCE"
/bin/rm -f "$TMP_SOURCE"

PLIST="$APP_DIR/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string au.com.sportscave.files-helper" "$PLIST" 2>/dev/null || \
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier au.com.sportscave.files-helper" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes array" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0 dict" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLName string Sports Cave Files" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string sports-cave-files" "$PLIST"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP_DIR"
/usr/bin/open "$APP_DIR"
echo "Sports Cave desktop helper installed for: $ROOT"
