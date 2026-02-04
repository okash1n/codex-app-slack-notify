# Security

## Reporting a vulnerability

If you believe you've found a security issue, please open an issue with minimal details first (no secrets),
or contact the repository owner privately.

## Slack Webhook URLs

Slack Incoming Webhook URLs behave like secrets. Do not commit them to git or paste them into public issues.

This project supports reading the webhook URL from a local file:

- `~/.codex/codex-notify-slack/webhook_url` (recommended)
