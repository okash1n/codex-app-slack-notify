import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import codex_notify_slack as notify


class ParseKindListTests(unittest.TestCase):
    def test_parse_kind_list_empty(self) -> None:
        self.assertEqual(notify.parse_kind_list(""), set())
        self.assertEqual(notify.parse_kind_list(None), set())

    def test_parse_kind_list_trims_and_filters(self) -> None:
        self.assertEqual(notify.parse_kind_list("a,b , c"), {"a", "b", "c"})
        self.assertEqual(notify.parse_kind_list("a,, ,b"), {"a", "b"})


class ShouldForwardTests(unittest.TestCase):
    def test_allow_deny_empty(self) -> None:
        self.assertTrue(notify.should_forward("turn-complete", set(), set()))

    def test_allow_only(self) -> None:
        self.assertTrue(notify.should_forward("turn-complete", {"turn-complete"}, set()))
        self.assertFalse(notify.should_forward("permission", {"turn-complete"}, set()))

    def test_deny_only(self) -> None:
        self.assertFalse(notify.should_forward("wait", set(), {"wait"}))
        self.assertTrue(notify.should_forward("turn-complete", set(), {"wait"}))

    def test_deny_has_priority(self) -> None:
        self.assertFalse(notify.should_forward("wait", {"wait"}, {"wait"}))


class FormatSlackMessageTests(unittest.TestCase):
    def test_format_includes_kind_and_id(self) -> None:
        ctx = notify.NotificationContext(kind="turn-complete", conversation_id="conv1", turn=3)
        msg = notify.format_slack_message("turn-complete", ctx, "turn-3")
        self.assertEqual(msg, "`turn-complete: 3`")

    def test_format_includes_request_fields(self) -> None:
        ctx = notify.NotificationContext(
            kind="permission",
            conversation_id="conv2",
            request=7,
            request_kind="wait",
        )
        msg = notify.format_slack_message("permission", ctx, "approval-7")
        self.assertEqual(msg, "`permission: 7`")
        self.assertNotIn("request=", msg)
        self.assertNotIn("request_kind=", msg)

    def test_format_includes_notification_texts(self) -> None:
        ctx = notify.NotificationContext(kind="turn-complete")
        msg = notify.format_slack_message(
            "turn-complete",
            ctx,
            "turn-1",
            ["Codex", "ターン完了"],
        )
        self.assertEqual(msg, "ターン完了\n`turn-complete: 1`")

    def test_format_keeps_raw_id_when_no_digits(self) -> None:
        ctx = notify.NotificationContext(kind="permission")
        msg = notify.format_slack_message("permission", ctx, "approval-x", ["Codex", "承認"])
        self.assertEqual(msg, "承認\n`permission: approval-x`")

    def test_format_title_and_body(self) -> None:
        ctx = notify.NotificationContext(kind="turn-complete")
        msg = notify.format_slack_message(
            "turn-complete",
            ctx,
            "turn-58",
            ["Codex", "スレッドタイトル", "本文"],
        )
        self.assertEqual(msg, "スレッドタイトル | 本文\n`turn-complete: 58`")


class NotificationTextParseTests(unittest.TestCase):
    def test_parse_notification_windows(self) -> None:
        raw = "Codex\tタイトル\t\nOther\tBody\t\n"
        windows = notify.parse_notification_windows(raw)
        self.assertEqual(windows, [["Codex", "タイトル"], ["Other", "Body"]])

    def test_filter_notification_texts(self) -> None:
        texts = ["Codex", "たった今", "本文", "本文", "1m"]
        filtered = notify.filter_notification_texts(texts)
        self.assertEqual(filtered, ["Codex", "本文"])


if __name__ == "__main__":
    unittest.main()
