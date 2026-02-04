# Codex macOS通知 -> Slack

English README: [README.md](./README.md)

Codex Desktop（macOS限定）のログから通知イベント（例: `turn-complete`）を検知して Slack に投稿します。

![Slack通知の稼働イメージ](https://github.com/user-attachments/assets/8dfc2af4-01e3-4b20-a514-5dea2024dbf7)

macOSの通知本文はログだけでは取れないため、**通知バナーUIを読む Helper.app**（AppleScript）を併用して本文/タイトルを拾います。

## 出力フォーマット

Slackに以下の形式で投稿します（2行）:

```text
スレッドタイトル | 本文
`turn-complete: 58`
```

本文が取れない場合は下の行だけになります:

```text
`turn-complete: 58`
```

## Requirements

- macOS
- `/usr/bin/python3`（標準ライブラリのみで動作）
- Slack Incoming Webhook

## Setup

### 1) Slack Incoming Webhook を作る

- Slack側で Incoming Webhook を有効化して、通知用チャンネルに紐づけた Webhook URL を取得します。
- Slackアプリを作成（[Your Apps](https://api.slack.com/apps) の「Create New App」）
- アプリ設定で「Incoming Webhooks」を有効化（Activate Incoming Webhooks をON）
- 「Add New Webhook to Workspace」から投稿先チャンネルを選択してURL発行（Authorize）
- private channel に投稿する場合は、そのチャンネルに参加しておく必要があります
- 公式手順: [Slack公式: Sending messages using incoming webhooks](https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/)

### 2) Webhook URL を保存

```bash
mkdir -p "$HOME/.codex/codex-notify-slack"
printf '%s' 'https://hooks.slack.com/services/XXX/YYY/ZZZ' > "$HOME/.codex/codex-notify-slack/webhook_url"
chmod 600 "$HOME/.codex/codex-notify-slack/webhook_url"
```

### 3) Helper.app を生成

```bash
./scripts/build-helper.sh
```

生成先（デフォルト）:

- `~/Applications/CodexNotifySlackHelper.app`

### 4) 権限（最重要）

システム設定で `CodexNotifySlackHelper.app` を許可します。

- 「プライバシーとセキュリティ > アクセシビリティ」: `CodexNotifySlackHelper.app` をON
- 「プライバシーとセキュリティ > オートメーション」: `CodexNotifySlackHelper.app` が `System Events` を制御できるようにON

### 5) 手動実行（dry-run推奨）

```bash
python3 ./codex_notify_slack.py --dry-run
```

本番:

```bash
python3 ./codex_notify_slack.py
```

絞り込み（完全一致）:

```bash
python3 ./codex_notify_slack.py --deny-kinds wait
python3 ./codex_notify_slack.py --allow-kinds turn-complete,permission
```

`--allow-kinds` が空なら全送信、`--deny-kinds` は常に優先されます。

## Run At Login (LaunchAgent)

インストール:

```bash
./scripts/install-launchagent.sh
```

アンインストール:

```bash
./scripts/uninstall-launchagent.sh
```

ログ:

```bash
tail -f /tmp/codex-notify-slack.out
tail -f /tmp/codex-notify-slack.err
```

手で触りたい場合は `launchagent/com.openai.codex.notify-slack.plist.example` も参照できます。

## Troubleshooting

- 本文が来ない/`-25211` が出る: `CodexNotifySlackHelper.app` のアクセシビリティ許可が入っていません
- `-1743` が出る: オートメーションで `System Events` の許可が入っていません
- 文字化け/例外で落ちる: Helper.app の出力エンコーディングは環境で変わるので、`/tmp/codex-notify-slack.err` を確認してください

## How It Works (ざっくり)

- Codex Desktop は `~/Library/Logs/com.openai.codex/**/codex-desktop-*-t0-*.log` にログを吐きます
- その中の `[desktop-notifications] forward show ...` をトリガーに Slack へ投稿します
- 通知本文/タイトルは Helper.app が通知バナーUIから取得します
