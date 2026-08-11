#!/usr/bin/env python3
"""Send a test Telegram message to verify bot integration."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.telegram.notifier import TelegramNotifier


def main() -> int:
    notifier = TelegramNotifier()
    if not notifier.is_configured():
        print("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env")
        return 1
    if notifier.send_test_message():
        print("Test message sent successfully.")
        return 0
    print("Failed to send test message.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
