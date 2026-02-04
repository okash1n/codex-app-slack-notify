#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
import subprocess
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


LOG_ROOT_DEFAULT = os.path.expanduser("~/Library/Logs/com.openai.codex")
WEBHOOK_FILE_DEFAULT = os.path.expanduser("~/.codex/codex-notify-slack/webhook_url")
STATE_FILE_DEFAULT = os.path.expanduser("~/.codex/codex-notify-slack/state.json")
NOTIFICATION_APP_NAME = "Codex"
NOTIFICATION_SCAN_TIMEOUT_S = 3.0
NOTIFICATION_SCAN_INTERVAL_S = 0.1
NOTIFICATION_PROCESS_NAMES = ("NotificationCenter", "UserNotificationCenter")
NOTIFICATION_HELPER_APP_DEFAULT = os.path.expanduser("~/Applications/CodexNotifySlackHelper.app")
NOTIFICATION_HELPER_OUTPUT = "/tmp/codex-notify-slack-notification.txt"
HELPER_WARNING_EMITTED = False

FORWARD_SHOW_RE = re.compile(
    r"\[desktop-notifications\] forward show id=(?P<id>\S+) kind=(?P<kind>\S+)"
)
SHOW_TURN_COMPLETE_RE = re.compile(
    r"\[desktop-notifications\] show turn-complete conv=(?P<conv>\S+) turn=(?P<turn>\d+)"
)
SHOW_APPROVAL_RE = re.compile(
    r"\[desktop-notifications\] show approval conv=(?P<conv>\S+) request=(?P<request>\d+) kind=(?P<request_kind>\S+)"
)
TIME_TEXT_RE = re.compile(
    r"^(now|Now|たった今|今|\d+[smh]|\d+秒前|\d+分前|\d+時間前)$"
)


@dataclass
class NotificationContext:
    kind: str
    conversation_id: Optional[str] = None
    turn: Optional[int] = None
    request: Optional[int] = None
    request_kind: Optional[str] = None


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def load_text_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return fp.read().strip()
    except FileNotFoundError:
        return None


def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path_obj.with_suffix(path_obj.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2, sort_keys=True)
        fp.write("\n")
    os.replace(tmp_path, path_obj)


def load_state(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, dict):
            return data
        return {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        eprint(f"[codex-notify-slack] state read error: {exc}")
        return {}


def find_latest_codex_log(log_root: str) -> Optional[str]:
    root = Path(log_root).expanduser()
    if not root.exists():
        return None

    def pick_newest_log_in_dir(dir_path: Path) -> Optional[Path]:
        newest: Optional[Path] = None
        newest_mtime = -1.0
        try:
            for path in dir_path.glob("*.log"):
                name = path.name
                if "codex-desktop-" not in name:
                    continue
                if "-t0-" not in name:
                    continue
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    continue
                if stat.st_mtime > newest_mtime:
                    newest_mtime = stat.st_mtime
                    newest = path
        except Exception:
            return None
        return newest

    # Fast path: logs are stored under YYYY/MM/DD.
    try:
        year_dirs = [p for p in root.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 4]
        if year_dirs:
            year_dir = max(year_dirs, key=lambda p: p.name)
            month_dirs = [p for p in year_dir.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 2]
            if month_dirs:
                month_dir = max(month_dirs, key=lambda p: p.name)
                day_dirs = [p for p in month_dir.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 2]
                if day_dirs:
                    day_dir = max(day_dirs, key=lambda p: p.name)
                    newest = pick_newest_log_in_dir(day_dir)
                    if newest:
                        return str(newest)
    except Exception:
        # Fall back to a full scan below.
        pass

    # Slow path fallback: scan everything.
    newest_path: Optional[Path] = None
    newest_mtime = -1.0
    try:
        for path in root.rglob("*.log"):
            name = path.name
            if "codex-desktop-" not in name:
                continue
            if "-t0-" not in name:
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            if stat.st_mtime > newest_mtime:
                newest_mtime = stat.st_mtime
                newest_path = path
    except Exception as exc:
        eprint(f"[codex-notify-slack] log scan error: {exc}")
        return None

    return str(newest_path) if newest_path else None


def slack_post(webhook_url: str, text: str, timeout_s: int = 10) -> None:
    payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        if resp.status >= 400:
            raise RuntimeError(f"Slack webhook HTTP {resp.status}: {body}")


def parse_kind_list(value: Optional[str]) -> set[str]:
    if not value:
        return set()
    parts = [item.strip() for item in value.split(",")]
    return {item for item in parts if item}


def should_forward(kind: str, allow_kinds: set[str], deny_kinds: set[str]) -> bool:
    if kind in deny_kinds:
        return False
    if not allow_kinds:
        return True
    return kind in allow_kinds


def run_osascript(script: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        if stderr:
            eprint(f"[codex-notify-slack] osascript failed: {stderr}")
        return None
    return proc.stdout


def parse_notification_windows(raw: str) -> list[list[str]]:
    windows: list[list[str]] = []
    for line in raw.splitlines():
        parts = [part.strip() for part in line.split("\t") if part.strip()]
        if parts:
            windows.append(parts)
    return windows


def filter_notification_texts(texts: list[str]) -> list[str]:
    filtered: list[str] = []
    seen = set()
    for text in texts:
        cleaned = text.strip()
        if not cleaned:
            continue
        if TIME_TEXT_RE.match(cleaned):
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        filtered.append(cleaned)
    return filtered


def select_notification_window(windows: list[list[str]], app_name: str) -> list[str]:
    if not windows:
        return []
    for win in windows:
        if any(app_name in text for text in win):
            return win
    # If we can't identify by app name, prefer the most recent banner.
    # In practice the last window tends to be the latest notification.
    return windows[-1]


def build_notification_script(process_name: str) -> str:
    script = """
tell application "System Events"
  tell process "__PROCESS__"
    set output to ""
    repeat with w in windows
      set textList to {}
      set elems to entire contents of w
      repeat with e in elems
        try
          if (role of e) is "AXStaticText" then
            set tval to ""
            try
              set tval to (value of e)
            end try
            if tval is missing value or tval is "" then
              try
                set tval to (name of e)
              end try
            end if
            if tval is not missing value and tval is not "" then
              set end of textList to tval
            end if
          end if
        end try
      end repeat
      if (count of textList) > 0 then
        set windowLine to ""
        repeat with t in textList
          set windowLine to windowLine & t & tab
        end repeat
        set output to output & windowLine & linefeed
      end if
    end repeat
    return output
  end tell
end tell
"""
    return script.replace("__PROCESS__", process_name)


def read_text_file(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as fp:
            data = fp.read()
    except FileNotFoundError:
        return None
    except Exception as exc:
        eprint(f"[codex-notify-slack] read error: {exc}")
        return None

    if not data:
        return ""

    # AppleScript applets may emit text in a non-UTF-8 encoding depending on the system locale.
    for enc in ("utf-8", "utf-8-sig", "cp932", "shift_jis", "mac_roman"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def fetch_notification_texts_via_helper(app_path: str, app_name: str) -> list[str]:
    if not os.path.exists(app_path):
        return []
    try:
        os.remove(NOTIFICATION_HELPER_OUTPUT)
    except FileNotFoundError:
        pass
    start = time.monotonic()
    subprocess.run(
        ["/usr/bin/open", "-a", app_path, "-n"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    deadline = time.monotonic() + NOTIFICATION_SCAN_TIMEOUT_S
    while time.monotonic() < deadline:
        raw = read_text_file(NOTIFICATION_HELPER_OUTPUT)
        if raw:
            windows = parse_notification_windows(raw)
            if windows:
                selected = select_notification_window(windows, app_name)
                return filter_notification_texts(selected)
        time.sleep(NOTIFICATION_SCAN_INTERVAL_S)
    return []


def fetch_notification_texts(app_name: str, helper_app: str) -> list[str]:
    global HELPER_WARNING_EMITTED
    deadline = time.monotonic() + NOTIFICATION_SCAN_TIMEOUT_S
    helper_exists = bool(helper_app) and os.path.exists(helper_app)
    while time.monotonic() < deadline:
        if helper_exists:
            helper_texts = fetch_notification_texts_via_helper(helper_app, app_name)
            if helper_texts:
                return helper_texts
            if not HELPER_WARNING_EMITTED:
                eprint(
                    "[codex-notify-slack] notification helper returned no data. "
                    "Check Accessibility permission for the helper app."
                )
                HELPER_WARNING_EMITTED = True
        else:
            for process_name in NOTIFICATION_PROCESS_NAMES:
                raw = run_osascript(build_notification_script(process_name))
                if raw:
                    windows = parse_notification_windows(raw)
                    if windows:
                        selected = select_notification_window(windows, app_name)
                        return filter_notification_texts(selected)
        time.sleep(NOTIFICATION_SCAN_INTERVAL_S)
    return []


def format_slack_message(
    kind: str,
    ctx: Optional[NotificationContext],
    raw_id: str,
    notification_texts: Optional[list[str]] = None,
) -> str:
    title = None
    body = None
    if notification_texts:
        body_texts = [text for text in notification_texts if text != NOTIFICATION_APP_NAME]
        if not body_texts:
            body_texts = notification_texts
        if len(body_texts) >= 2:
            title = body_texts[0]
            body = " / ".join(body_texts[1:]) or None
        else:
            body = body_texts[0]

    id_value = raw_id
    match = re.search(r"(\d+)", raw_id)
    if match:
        id_value = match.group(1)

    header = f"`{kind}: {id_value}`"
    if not title and not body:
        return header

    if title and body:
        return f"{title} | {body}\n{header}"
    if title:
        return f"{title}\n{header}"
    return f"{body}\n{header}"


def parse_context_line(line: str) -> Optional[NotificationContext]:
    m = SHOW_TURN_COMPLETE_RE.search(line)
    if m:
        return NotificationContext(
            kind="turn-complete",
            conversation_id=m.group("conv"),
            turn=int(m.group("turn")),
        )

    m = SHOW_APPROVAL_RE.search(line)
    if m:
        return NotificationContext(
            kind="permission",
            conversation_id=m.group("conv"),
            request=int(m.group("request")),
            request_kind=m.group("request_kind"),
        )

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Forward Codex desktop notification events to Slack.")
    parser.add_argument("--log-root", default=LOG_ROOT_DEFAULT, help="Codex log root directory")
    parser.add_argument("--webhook-url", default=None, help="Slack Incoming Webhook URL (optional)")
    parser.add_argument(
        "--webhook-file",
        default=WEBHOOK_FILE_DEFAULT,
        help="File containing Slack Incoming Webhook URL",
    )
    parser.add_argument("--state-file", default=STATE_FILE_DEFAULT, help="State file path")
    parser.add_argument(
        "--from-beginning",
        action="store_true",
        help="If state is empty, start reading from beginning (may replay old notifications).",
    )
    parser.add_argument(
        "--allow-kinds",
        default="",
        help="Comma-separated kind allowlist (exact match). Empty=allow all.",
    )
    parser.add_argument(
        "--deny-kinds",
        default="",
        help="Comma-separated kind denylist (exact match). Deny has priority.",
    )
    parser.add_argument(
        "--notification-helper",
        default=NOTIFICATION_HELPER_APP_DEFAULT,
        help="App bundle path used to read notification UI (for Accessibility permission).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print instead of posting to Slack")
    parser.add_argument("--rescan-interval", type=float, default=5.0, help="Seconds between log file rescans")
    parser.add_argument("--idle-sleep", type=float, default=0.5, help="Seconds to sleep when no new data")
    args = parser.parse_args()

    webhook_url = args.webhook_url or os.environ.get("SLACK_WEBHOOK_URL") or load_text_file(args.webhook_file)
    if not webhook_url and not args.dry_run:
        eprint(
            "[codex-notify-slack] Slack webhook URL not set. "
            "Set SLACK_WEBHOOK_URL or write it to: "
            f"{args.webhook_file}"
        )
        return 2
    if not webhook_url:
        webhook_url = ""

    allow_kinds = parse_kind_list(args.allow_kinds)
    deny_kinds = parse_kind_list(args.deny_kinds)

    state = load_state(args.state_file)
    current_path: Optional[str] = None
    fp: Optional[Any] = None
    recent_lines: deque[str] = deque(maxlen=20)
    context_by_id: Dict[str, NotificationContext] = {}
    last_rescan = 0.0

    def open_log(path: str) -> None:
        nonlocal current_path, fp, recent_lines, context_by_id, state
        if fp:
            try:
                fp.close()
            except Exception:
                pass
        fp = open(path, "r", encoding="utf-8", errors="replace")
        current_path = path
        recent_lines.clear()
        context_by_id.clear()

        # Restore position if we were already tracking this file; otherwise start at end (default).
        saved_file = state.get("file")
        saved_pos = state.get("pos")
        if saved_file == path and isinstance(saved_pos, int) and saved_pos >= 0:
            try:
                fp.seek(saved_pos)
            except Exception:
                fp.seek(0, os.SEEK_END)
        else:
            if args.from_beginning:
                fp.seek(0, os.SEEK_SET)
            else:
                fp.seek(0, os.SEEK_END)
            state["file"] = path
            state["pos"] = fp.tell()
            atomic_write_json(args.state_file, state)

        print(f"[codex-notify-slack] following: {path}")

    def maybe_rescan_and_switch(force: bool = False) -> None:
        nonlocal last_rescan
        now = time.time()
        if not force and (now - last_rescan) < float(args.rescan_interval):
            return
        last_rescan = now
        latest = find_latest_codex_log(args.log_root)
        if not latest:
            return
        if latest != current_path:
            open_log(latest)

    maybe_rescan_and_switch(force=True)
    if not current_path or not fp:
        eprint(f"[codex-notify-slack] Codex log not found under: {args.log_root}")
        return 3

    line_count_since_state_write = 0
    while True:
        line = fp.readline()
        if not line:
            maybe_rescan_and_switch()
            time.sleep(float(args.idle_sleep))
            continue

        recent_lines.append(line.strip())
        line_count_since_state_write += 1

        # Update context cache.
        ctx = parse_context_line(line)
        if ctx:
            if ctx.kind == "turn-complete" and ctx.turn is not None:
                context_by_id[f"turn-{ctx.turn}"] = ctx
            elif ctx.kind == "permission" and ctx.request is not None:
                context_by_id[f"approval-{ctx.request}"] = ctx

        # Trigger on forward-show.
        m = FORWARD_SHOW_RE.search(line)
        if m:
            notif_id = m.group("id")
            kind = m.group("kind")
            if not should_forward(kind, allow_kinds, deny_kinds):
                continue
            ctx_for_id = context_by_id.get(notif_id)
            notification_texts = fetch_notification_texts(NOTIFICATION_APP_NAME, args.notification_helper)
            text = format_slack_message(kind, ctx_for_id, notif_id, notification_texts)
            if args.dry_run:
                print(text)
            else:
                try:
                    slack_post(webhook_url, text)
                except Exception as exc:
                    eprint(f"[codex-notify-slack] Slack post failed: {exc}")

        # Persist state occasionally.
        if line_count_since_state_write >= 50:
            state["file"] = current_path
            state["pos"] = fp.tell()
            atomic_write_json(args.state_file, state)
            line_count_since_state_write = 0


if __name__ == "__main__":
    raise SystemExit(main())
