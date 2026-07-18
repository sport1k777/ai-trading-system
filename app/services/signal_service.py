"""24/7 continuous Telegram signal service built on the existing AI pipeline."""

from __future__ import annotations

import logging
import signal
import sys
import time
from typing import Optional

from app.config import (
    DEFAULT_INTERVAL,
    PRO_V2_HTF_INTERVAL,
    SCANNER_SYMBOLS,
    SIGNAL_ENGINE_VERSION,
    SIGNAL_SERVICE_ERROR_BACKOFF_SECONDS,
    SIGNAL_SERVICE_RECONNECT_AFTER_ERRORS,
    SIGNAL_SERVICE_SCAN_INTERVAL_SECONDS,
    SIGNAL_SERVICE_SENT_STORE_PATH,
    TELEGRAM_NOTIFY_MIN_CONFIDENCE,
)
from app.diagnostics.pipeline_diagnostic import diagnose_scan, format_diagnostic_block
from app.pipeline import TradingPipeline
from app.telegram.formatter import format_live_signal_message
from app.telegram.notifier import TelegramNotifier
from app.telegram.signal_store import SentSignalRecord, SignalStore
from app.utils.logging_config import setup_logging
from app.utils.ssl_ca import ensure_ca_bundle

logger = logging.getLogger(__name__)


def _trace(stage: str, **fields) -> None:
    """Temporary production trace — remove after pipeline stall is confirmed fixed."""
    detail = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("TRACE %s%s", stage, f" | {detail}" if detail else "")


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

    def _fetch_htf_df(self, symbol: str):
        if SIGNAL_ENGINE_VERSION != "v2":
            return None
        try:
            return self.pipeline.collector.get_candles(
                symbol=symbol,
                interval=PRO_V2_HTF_INTERVAL,
                limit=120,
            )
        except Exception:
            logger.warning("%s: HTF fetch failed for diagnostic context", symbol)
            return None

    def _log_scan_diagnostic(self, result, *, htf_df=None) -> None:
        _trace("diagnostic.start", symbol=result.symbol)
        diag = diagnose_scan(
            result,
            timeframe=self.interval,
            min_confidence=self.min_confidence,
            htf_df=htf_df,
        )
        status = "ACCEPTED" if diag.would_alert else "REJECTED"
        _trace(
            "diagnostic.done",
            symbol=diag.symbol,
            status=status,
            confidence=f"{diag.confidence:.1f}",
            engine_signal=diag.engine_signal,
            final_decision=diag.final_decision,
        )
        logger.info(
            "Scan decision | symbol=%s confidence=%.1f status=%s reason=%s",
            diag.symbol,
            diag.confidence,
            status,
            diag.rejection_reason,
        )
        logger.info("Scan diagnostic\n%s", format_diagnostic_block(diag))

    def _process_symbol(self, symbol: str) -> bool:
        """Analyze one symbol and send Telegram alert when eligible. Returns True on success."""
        _trace("process_symbol.start", symbol=symbol)
        htf_df = self._fetch_htf_df(symbol)
        _trace(
            "process_symbol.htf",
            symbol=symbol,
            fetched=htf_df is not None,
        )
        _trace("process_symbol.analyze_call", symbol=symbol)
        result = self.pipeline.analyze(symbol=symbol, interval=self.interval)
        _trace(
            "process_symbol.analyze_returned",
            symbol=symbol,
            engine_signal=result.signal.get("signal"),
            confidence=result.signal.get("confidence", result.signal.get("confluence", 0)),
        )
        self._log_scan_diagnostic(result, htf_df=htf_df)

        signal = result.signal
        direction = signal.get("signal")

        if direction not in ("BUY", "SELL"):
            _trace(
                "process_symbol.no_actionable_signal",
                symbol=symbol,
                direction=direction,
            )
            return True

        confidence = float(signal.get("confidence", signal.get("confluence", 0)))
        if confidence < self.min_confidence:
            _trace(
                "process_symbol.telegram_blocked_confidence",
                symbol=symbol,
                direction=direction,
                confidence=f"{confidence:.1f}",
                min_confidence=f"{self.min_confidence:.1f}",
            )
            logger.info(
                "%s: Telegram gate — confidence %.1f below threshold %.1f",
                symbol,
                confidence,
                self.min_confidence,
            )
            return True

        reasons = signal.get("reasons") or []
        pass_reason = reasons[0] if reasons else (
            f"Engine {direction} signal confidence {confidence:.1f} "
            f">= Telegram threshold {self.min_confidence:.0f}"
        )
        logger.info(
            "Telegram gate PASSED | symbol=%s direction=%s confidence=%.1f reason=%s",
            symbol,
            direction,
            confidence,
            pass_reason,
        )

        risk = result.risk
        if not risk:
            _trace(
                "process_symbol.telegram_blocked_no_risk",
                symbol=symbol,
                direction=direction,
                confidence=f"{confidence:.1f}",
            )
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
            _trace(
                "process_symbol.telegram_blocked_duplicate",
                symbol=symbol,
                direction=direction,
                entry=f"{record.entry:.4f}",
            )
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
            _trace(
                "process_symbol.telegram_blocked_formatter",
                symbol=symbol,
                direction=direction,
            )
            return True

        _trace("process_symbol.telegram_send", symbol=symbol, direction=direction)
        if not self.notifier.send_message(message):
            logger.error("%s: failed to send Telegram alert", symbol)
            return False

        self.store.record(record)
        _trace(
            "process_symbol.telegram_sent",
            symbol=symbol,
            direction=direction,
            grade=grade,
            confidence=f"{confidence:.1f}",
        )
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
        _trace("run_cycle.start", symbols=len(self.symbols))
        failures = 0
        for symbol in self.symbols:
            try:
                ok = self._process_symbol(symbol)
                if not ok:
                    failures += 1
                _trace(
                    "run_cycle.symbol_done",
                    symbol=symbol,
                    ok=ok,
                    failures=failures,
                )
            except Exception:
                failures += 1
                _trace("run_cycle.symbol_failed", symbol=symbol, failures=failures)
                logger.exception("Unhandled error while scanning %s", symbol)
        _trace("run_cycle.done", failures=failures, symbols=len(self.symbols))
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
            _trace("run_forever.cycle_start")
            failures = self.run_cycle()
            _trace("run_forever.cycle_end", failures=failures)
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
    ensure_ca_bundle()
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
