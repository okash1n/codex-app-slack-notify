#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_LABEL="com.openai.codex.notify-slack"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
PYTHON3="/usr/bin/python3"
SCRIPT="$ROOT_DIR/codex_notify_slack.py"

if [[ ! -x "$PYTHON3" ]]; then
  echo "[codex-notify-slack] python3 not found at: $PYTHON3" >&2
  exit 1
fi
if [[ ! -f "$SCRIPT" ]]; then
  echo "[codex-notify-slack] script not found: $SCRIPT" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"

cat >"$PLIST_DST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
      <string>${PYTHON3}</string>
      <string>${SCRIPT}</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/codex-notify-slack.out</string>

    <key>StandardErrorPath</key>
    <string>/tmp/codex-notify-slack.err</string>
  </dict>
</plist>
EOF

# Reload agent (ignore errors when not previously loaded).
launchctl bootout "gui/$UID" "$PLIST_DST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID" "$PLIST_DST"
launchctl kickstart -k "gui/$UID/${PLIST_LABEL}" >/dev/null 2>&1 || true

echo "[codex-notify-slack] installed: $PLIST_DST"
