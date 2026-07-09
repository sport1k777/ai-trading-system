"""Persistent deduplication store for Telegram signal alerts."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _price_key(price: float) -> str:
    if price >= 100:
        return f"{price:.2f}"
    if price >= 1:
        return f"{price:.4f}"
    return f"{price:.6f}"


def build_setup_fingerprint(
    *,
    symbol: str,
    direction: str,
    entry: float,
    stop: float,
    tp1: float,
    timeframe: str,
) -> str:
    return "|".join(
        [
            symbol.upper(),
            direction.upper(),
            _price_key(entry),
            _price_key(stop),
            _price_key(tp1),
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

    @classmethod
    def from_result(
        cls,
        *,
        symbol: str,
        direction: str,
        risk: dict,
        confidence: float,
        timeframe: str,
    ) -> SentSignalRecord:
        fingerprint = build_setup_fingerprint(
            symbol=symbol,
            direction=direction,
            entry=float(risk["entry"]),
            stop=float(risk["stop"]),
            tp1=float(risk["tp1"]),
            timeframe=timeframe,
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
        )


class SignalStore:
    """Tracks the last sent setup per symbol to prevent duplicate alerts."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._records: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self._records = {}
            return

        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            self._records = data if isinstance(data, dict) else {}
            logger.info("Loaded %d sent-signal records from %s", len(self._records), self.path)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load signal store (%s); starting fresh", exc)
            self._records = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(self._records, handle, indent=2, sort_keys=True)
        tmp_path.replace(self.path)

    def get(self, symbol: str) -> Optional[SentSignalRecord]:
        raw = self._records.get(symbol.upper())
        if not raw:
            return None
        return SentSignalRecord(**raw)

    def is_duplicate(self, record: SentSignalRecord) -> bool:
        previous = self.get(record.symbol)
        if previous is None:
            return False
        return previous.fingerprint == record.fingerprint

    def record(self, sent: SentSignalRecord) -> None:
        self._records[sent.symbol.upper()] = asdict(sent)
        self.save()
        logger.info(
            "Recorded sent signal for %s (%s, conf=%.1f)",
            sent.symbol,
            sent.direction,
            sent.confidence,
        )
