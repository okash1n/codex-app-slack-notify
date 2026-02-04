# Codex macOS Notifications -> Slack

Japanese README: [README.ja.md](./README.ja.md)

This project watches Codex Desktop (macOS only) logs for notification events (for example, `turn-complete`) and posts them to Slack.

![Slack notification example](https://github.com/user-attachments/assets/8dfc2af4-01e3-4b20-a514-5dea2024dbf7)

Because notification body text is not available in logs alone, it uses a **Helper.app that reads the notification banner UI** (AppleScript) to capture the title/body.

## Output Format

It posts in this two-line format:

```text
Thread title | Body
`turn-complete: 58`
```

If the body cannot be read, only the second line is sent:

```text
`turn-complete: 58`
```

## Requirements

- macOS
- `/usr/bin/python3` (standard library only)
- Slack Incoming Webhook

## Setup

### 1) Create a Slack Incoming Webhook

- Enable Incoming Webhooks and get a webhook URL for your target channel.
- Create a Slack app at [Your Apps](https://api.slack.com/apps) (Create New App).
- Enable Incoming Webhooks (turn on Activate Incoming Webhooks).
- Use "Add New Webhook to Workspace" and authorize the target channel.
- For private channels, join the channel before adding the webhook.
- Official guide: [Sending messages using incoming webhooks](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/)

### 2) Store the Webhook URL

```bash
mkdir -p "$HOME/.codex/codex-notify-slack"
printf '%s' 'https://hooks.slack.com/services/XXX/YYY/ZZZ' > "$HOME/.codex/codex-notify-slack/webhook_url"
chmod 600 "$HOME/.codex/codex-notify-slack/webhook_url"
```

### 3) Build the Helper.app

```bash
./scripts/build-helper.sh
```

Default location:

- `~/Applications/CodexNotifySlackHelper.app`

### 4) Permissions (Important)

Allow `CodexNotifySlackHelper.app` in System Settings.

- Privacy & Security > Accessibility: enable `CodexNotifySlackHelper.app`
- Privacy & Security > Automation: allow `CodexNotifySlackHelper.app` to control `System Events`

### 5) Run manually (dry-run recommended)

```bash
python3 ./codex_notify_slack.py --dry-run
```

Production:

```bash
python3 ./codex_notify_slack.py
```

Filtering (exact match):

```bash
python3 ./codex_notify_slack.py --deny-kinds wait
python3 ./codex_notify_slack.py --allow-kinds turn-complete,permission
```

If `--allow-kinds` is empty, all kinds are allowed. `--deny-kinds` always takes priority.

## Run at Login (LaunchAgent)

Install:

```bash
./scripts/install-launchagent.sh
```

Uninstall:

```bash
./scripts/uninstall-launchagent.sh
```

Logs:

```bash
tail -f /tmp/codex-notify-slack.out
tail -f /tmp/codex-notify-slack.err
```

If you want to customize the plist directly, see `launchagent/com.openai.codex.notify-slack.plist.example`.

## Troubleshooting

- No body / `-25211`: Accessibility permission is missing for `CodexNotifySlackHelper.app`
- `-1743`: Automation permission for `System Events` is missing
- Garbled text or crashes: check `/tmp/codex-notify-slack.err` for encoding-related errors

## How It Works

- Codex Desktop writes logs to `~/Library/Logs/com.openai.codex/**/codex-desktop-*-t0-*.log`
- This tool watches for `[desktop-notifications] forward show ...` and posts to Slack
- The Helper.app reads the notification banner UI to extract title/body
