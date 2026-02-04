#!/usr/bin/env bash
set -euo pipefail

PLIST_LABEL="com.openai.codex.notify-slack"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

launchctl bootout "gui/$UID" "$PLIST_DST" >/dev/null 2>&1 || true
rm -f "$PLIST_DST"

echo "[codex-notify-slack] uninstalled: $PLIST_DST"
