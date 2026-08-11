"""Persistent deduplication store for Telegram signal alerts."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.config import SIGNAL_DUPLICATE_WINDOW_MINUTES

logger = logging.getLogger(__name__)


def _price_key(price: float) -> str:
    if price >= 100:
        return f"{price:.2f}"
    if price >= 1:
        return f"{price:.4f}"
    return f"{price:.6f}"


def _order_block_key(order_block: dict | None, direction: str) -> str:
    if not order_block:
        return "none"
    side = "bullish" if direction.upper() == "BUY" else "bearish"
    ob = order_block.get(side)
    if not ob:
        return "none"
    return f"{_price_key(float(ob['low']))}-{_price_key(float(ob['high']))}"


def build_setup_fingerprint(
    *,
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    tp1: float,
    timeframe: str,
    order_block: dict | None = None,
) -> str:
    return "|".join(
        [
            symbol.upper(),
            direction.upper(),
            _price_key(entry),
            _price_key(stop),
            _price_key(tp1),
            _order_block_key(order_block, direction),
            timeframe,
        ]
    )


@dataclass
class SentSignalRecord:
    symbol: str
    direction: str
    entry: float
    stop: float
    tp1: float
    tp2: float
    tp3: float
    confidence: float
    timeframe: str
    fingerprint: str
    sent_at: str
    order_block_key: str = "none"

    @classmethod
    def from_result(
        cls,
        *,
        symbol: str,
        direction: str,
        risk: dict,
        confidence: float,
        timeframe: str,
        order_block: dict | None = None,
    ) -> SentSignalRecord:
        ob_key = _order_block_key(order_block, direction)
        fingerprint = build_setup_fingerprint(
            symbol=symbol,
            direction=direction,
            entry=float(risk["entry"]),
            stop=float(risk["stop"]),
            tp1=float(risk["tp1"]),
            timeframe=timeframe,
            order_block=order_block,
        )
        return cls(
            symbol=symbol.upper(),
            direction=direction.upper(),
            entry=float(risk["entry"]),
            stop=float(risk["stop"]),
            tp1=float(risk["tp1"]),
            tp2=float(risk["tp2"]),
            tp3=float(risk["tp3"]),
            confidence=confidence,
            timeframe=timeframe,
            fingerprint=fingerprint,
            sent_at=datetime.now(timezone.utc).isoformat(),
            order_block_key=ob_key,
        )


class SignalStore:
    """Tracks recent sent setups to prevent duplicate alerts within a time window."""

    def __init__(self, path: str | Path, *, window_minutes: int | None = None):
        self.path = Path(path)
        self.window_minutes = (
            window_minutes if window_minutes is not None else SIGNAL_DUPLICATE_WINDOW_MINUTES
        )
        self._records: dict[str, list[dict]] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._records = {}
            return

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict) and data and all(isinstance(v, list) for v in data.values()):
                self._records = data
            elif isinstance(data, dict):
                # Migrate legacy single-record-per-symbol format.
                migrated: dict[str, list[dict]] = {}
                for sym, raw in data.items():
                    migrated[sym.upper()] = [raw] if isinstance(raw, dict) else []
                self._records = migrated
            else:
                self._records = {}
            self._prune_expired()
            logger.info(
                "Loaded sent-signal history for %d symbols from %s",
                len(self._records),
                self.path,
            )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load signal store (%s); starting fresh", exc)
            self._records = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self._records, handle, indent=2, sort_keys=True)
        tmp_path.replace(self.path)

    def _parse_sent_at(self, sent_at: str) -> datetime | None:
        try:
            dt = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (TypeError, ValueError):
            return None

    def _prune_expired(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.window_minutes)
        for symbol in list(self._records.keys()):
            kept = []
            for raw in self._records[symbol]:
                sent = self._parse_sent_at(raw.get("sent_at", ""))
                if sent and sent >= cutoff:
                    kept.append(raw)
            if kept:
                self._records[symbol] = kept
            else:
                del self._records[symbol]

    def recent(self, symbol: str) -> list[SentSignalRecord]:
        self._prune_expired()
        rows = self._records.get(symbol.upper(), [])
        return [SentSignalRecord(**raw) for raw in rows]

    def is_duplicate(self, record: SentSignalRecord) -> bool:
        """True when the same symbol/direction/setup/OB was sent within the window."""
        self._prune_expired()
        for previous in self.recent(record.symbol):
            if previous.fingerprint == record.fingerprint:
                logger.info(
                    "Duplicate suppressed | %s %s fingerprint=%s sent_at=%s",
                    record.symbol,
                    record.direction,
                    record.fingerprint,
                    previous.sent_at,
                )
                return True
        return False

    def record(self, sent: SentSignalRecord) -> None:
        self._prune_expired()
        sym = sent.symbol.upper()
        history = self._records.setdefault(sym, [])
        history.append(asdict(sent))
        self._records[sym] = history[-20:]
        self.save()
        logger.info(
            "Recorded sent signal for %s (%s, conf=%.1f, ob=%s)",
            sent.symbol,
            sent.direction,
            sent.confidence,
            sent.order_block_key,
        )
