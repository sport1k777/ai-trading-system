"""Telegram notifications for high-confidence AI signals."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Optional

from app.config import (
    DEFAULT_INTERVAL,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ENABLED,
    TELEGRAM_NOTIFY_MIN_CONFIDENCE,
)
from app.telegram.formatter import format_signal_message, format_test_message

if TYPE_CHECKING:
    from app.pipeline import AnalysisResult

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Send formatted trading signals via Telegram Bot API."""

    def __init__(
        self,
        *,
        bot_token: str | None = None,
        chat_id: str | None = None,
        enabled: bool | None = None,
        min_confidence: float | None = None,
    ):
        self.bot_token = bot_token if bot_token is not None else TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id if chat_id is not None else TELEGRAM_CHAT_ID
        self.enabled = TELEGRAM_ENABLED if enabled is None else enabled
        self.min_confidence = (
            TELEGRAM_NOTIFY_MIN_CONFIDENCE if min_confidence is None else min_confidence
        )

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def is_enabled(self) -> bool:
        return self.enabled and self.is_configured()

    def send_message(self, text: str, *, parse_mode: str | None = "MarkdownV2") -> bool:
        if not self.is_enabled():
            logger.warning("Telegram notifications disabled or not configured")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload: dict = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = json.loads(response.read().decode("utf-8"))
                if not body.get("ok"):
                    logger.error("Telegram API error: %s", body)
                    return False
                return True
        except urllib.error.HTTPError as exc:
            logger.error("Telegram HTTP error: %s", exc.read().decode("utf-8", errors="replace"))
            return False
        except urllib.error.URLError as exc:
            logger.error("Telegram request failed: %s", exc)
            return False

    def format_signal_message(
        self,
        result: AnalysisResult,
        *,
        timeframe: str | None = None,
    ) -> Optional[str]:
        return format_signal_message(
            result,
            timeframe=timeframe,
            min_confidence=self.min_confidence,
        )

    def notify_signal(
        self,
        result: AnalysisResult,
        *,
        timeframe: str | None = None,
    ) -> bool:
        message = self.format_signal_message(result, timeframe=timeframe)
        if not message:
            return False
        return self.send_message(message)

    def send_test_message(self) -> bool:
        return self.send_message(format_test_message())


def notify_high_confidence_signal(
    result: AnalysisResult,
    *,
    timeframe: str | None = None,
) -> bool:
    """Send Telegram alert when signal confidence meets threshold."""
    notifier = TelegramNotifier()
    if not notifier.is_enabled():
        return False
    return notifier.notify_signal(result, timeframe=timeframe)
