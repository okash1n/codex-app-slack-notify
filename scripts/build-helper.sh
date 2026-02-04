#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_APP="${1:-$HOME/Applications/CodexNotifySlackHelper.app}"
BUNDLE_ID="com.openai.codex.notify-slack.helper"

mkdir -p "$(dirname -- "$OUT_APP")"

rm -rf "$OUT_APP"
osacompile -o "$OUT_APP" "$ROOT_DIR/assets/notification_reader.applescript"

# Ensure a stable bundle id so macOS can remember permissions.
/usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $BUNDLE_ID" "$OUT_APP/Contents/Info.plist" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$OUT_APP/Contents/Info.plist"

# Ad-hoc sign so LaunchServices/TCC treat it as a normal app bundle.
codesign --force --deep --sign - --identifier "$BUNDLE_ID" "$OUT_APP" >/dev/null

# Best-effort: register with LaunchServices so it shows up in System Settings lists.
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [[ -x "$LSREGISTER" ]]; then
  "$LSREGISTER" -f "$OUT_APP" >/dev/null 2>&1 || true
fi

echo "[codex-notify-slack] helper built: $OUT_APP"
