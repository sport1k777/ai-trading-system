"""24/7 continuous Telegram signal service built on the existing AI pipeline."""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Optional

from app.config import (
    DEFAULT_INTERVAL,
    SCANNER_SYMBOLS,
    SIGNAL_SERVICE_ERROR_BACKOFF_SECONDS,
    SIGNAL_SERVICE_RECONNECT_AFTER_ERRORS,
    SIGNAL_SERVICE_SCAN_INTERVAL_SECONDS,
    SIGNAL_SERVICE_SENT_STORE_PATH,
    TELEGRAM_NOTIFY_MIN_CONFIDENCE,
)
from app.pipeline import TradingPipeline
from app.telegram.formatter import format_live_signal_message
from app.telegram.notifier import TelegramNotifier
from app.telegram.signal_store import SentSignalRecord, SignalStore
from app.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class SignalService:
    """Scans configured symbols continuously and sends deduplicated Telegram alerts."""

    def __init__(
        self,
        *,
        symbols: list[str] | None = None,
        scan_interval_seconds: int | None = None,
        min_confidence: float | None = None,
        interval: str | None = None,
        store_path: str | None = None,
    ):
        self.symbols = symbols or SCANNER_SYMBOLS
        self.scan_interval_seconds = (
            scan_interval_seconds or SIGNAL_SERVICE_SCAN_INTERVAL_SECONDS
        )
        self.min_confidence = min_confidence or TELEGRAM_NOTIFY_MIN_CONFIDENCE
        self.interval = interval or DEFAULT_INTERVAL
        self.store = SignalStore(store_path or SIGNAL_SERVICE_SENT_STORE_PATH)
        self.notifier = TelegramNotifier(min_confidence=self.min_confidence)
        self.pipeline = TradingPipeline()
        self._running = False
        self._consecutive_cycle_failures = 0

    def reconnect(self) -> None:
        logger.warning("Reconnecting Bybit client and rebuilding pipeline")
        try:
            if hasattr(self.pipeline.collector, "client") and hasattr(
                self.pipeline.collector.client, "reconnect"
            ):
                self.pipeline.collector.client.reconnect()
            else:
                self.pipeline = TradingPipeline()
        except Exception:
            logger.exception("Reconnect failed; creating fresh pipeline")
            self.pipeline = TradingPipeline()
        self._consecutive_cycle_failures = 0

    def _process_symbol(self, symbol: str) -> bool:
        """Analyze one symbol and send Telegram alert when eligible. Returns True on success."""
        result = self.pipeline.analyze(symbol=symbol, interval=self.interval)
        signal = result.signal
        direction = signal.get("signal")

        if direction not in ("BUY", "SELL"):
            logger.debug("%s: no actionable signal (%s)", symbol, direction)
            return True

        confidence = float(signal.get("confidence", signal.get("confluence", 0)))
        if confidence < self.min_confidence:
            logger.debug(
                "%s: confidence %.1f below threshold %.1f",
                symbol,
                confidence,
                self.min_confidence,
            )
            return True

        risk = result.risk
        if not risk:
            logger.warning("%s: high-confidence %s but no risk levels", symbol, direction)
            return True

        record = SentSignalRecord.from_result(
            symbol=symbol,
            direction=direction,
            risk=risk,
            confidence=confidence,
            timeframe=self.interval,
        )

        grade = signal.get("grade", "n/a")

        if self.store.is_duplicate(record):
            logger.info(
                "%s: duplicate setup suppressed (%s @ %.4f)",
                symbol,
                direction,
                record.entry,
            )
            return True

        message = format_live_signal_message(
            result,
            timeframe=self.interval,
            min_confidence=self.min_confidence,
        )
        if not message:
            return True

        if not self.notifier.send_message(message):
            logger.error("%s: failed to send Telegram alert", symbol)
            return False

        self.store.record(record)
        logger.info(
            "%s: Telegram alert sent (%s, grade=%s, confidence=%.1f)",
            symbol,
            direction,
            grade,
            confidence,
        )
        return True

    def run_cycle(self) -> int:
        """Run one full scan across all symbols. Returns number of symbol-level failures."""
        failures = 0
        for symbol in self.symbols:
            try:
                if not self._process_symbol(symbol):
                    failures += 1
            except Exception:
                failures += 1
                logger.exception("Unhandled error while scanning %s", symbol)
        return failures

    def _sleep_until_next_cycle(self, cycle_started: float) -> None:
        elapsed = time.monotonic() - cycle_started
        remaining = self.scan_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _handle_cycle_failures(self, failures: int) -> None:
        if failures == 0:
            self._consecutive_cycle_failures = 0
            return

        if failures < len(self.symbols):
            logger.warning(
                "Cycle completed with %d/%d symbol failures",
                failures,
                len(self.symbols),
            )
            return

        self._consecutive_cycle_failures += 1
        logger.error(
            "Full cycle failed (%d consecutive)",
            self._consecutive_cycle_failures,
        )

        if self._consecutive_cycle_failures >= SIGNAL_SERVICE_RECONNECT_AFTER_ERRORS:
            self.reconnect()

        backoff = min(
            300,
            SIGNAL_SERVICE_ERROR_BACKOFF_SECONDS * self._consecutive_cycle_failures,
        )
        logger.warning("Backing off for %ds before next cycle", backoff)
        time.sleep(backoff)

    def run_forever(self) -> None:
        self._running = True
        logger.info(
            "Signal service started | symbols=%s | interval=%ss | tf=%sm | min_conf=%.1f",
            ",".join(self.symbols),
            self.scan_interval_seconds,
            self.interval,
            self.min_confidence,
        )

        if self.notifier.is_enabled():
            self.notifier.send_message(
                "🚀 *AI Signal Service Online*\n\n"
                f"Scanning `{len(self.symbols)}` symbols every "
                f"`{self.scan_interval_seconds}s`\\.\n"
                f"Alerts fire at confidence ≥ `{self.min_confidence:.0f}`\\.",
            )
        else:
            logger.warning("Telegram is disabled or not configured")

        while self._running:
            cycle_started = time.monotonic()
            failures = self.run_cycle()
            self._handle_cycle_failures(failures)
            if self._running:
                self._sleep_until_next_cycle(cycle_started)

        logger.info("Signal service stopped")

    def stop(self) -> None:
        self._running = False


_service: Optional[SignalService] = None


def _handle_shutdown(signum, _frame) -> None:
    logger.info("Received signal %s; shutting down gracefully", signum)
    if _service is not None:
        _service.stop()


def main() -> None:
    global _service
    setup_logging("app.services.signal_service")
    _service = SignalService()

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    try:
        _service.run_forever()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception:
        logger.exception("Fatal error in signal service")
        sys.exit(1)


if __name__ == "__main__":
    main()
