"""Tests for Telegram signal deduplication store."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.telegram.signal_store import (
    SentSignalRecord,
    SignalStore,
    build_setup_fingerprint,
)


def test_build_setup_fingerprint_stable():
    ob = {"bullish": {"low": 64000.0, "high": 64500.0}}
    fp1 = build_setup_fingerprint(
        symbol="BTCUSDT",
        direction="BUY",
        entry=65000.123,
        stop=64000.456,
        tp1=66000.789,
        timeframe="15",
        order_block=ob,
    )
    fp2 = build_setup_fingerprint(
        symbol="btcusdt",
        direction="buy",
        entry=65000.12,
        stop=64000.46,
        tp1=66000.79,
        timeframe="15",
        order_block=ob,
    )
    assert fp1 == fp2


def test_signal_store_deduplicates_same_setup(tmp_path: Path):
    store_path = tmp_path / "sent.json"
    store = SignalStore(store_path, window_minutes=30)

    ob = {"bullish": {"low": 95.0, "high": 101.0}}
    risk = {
        "entry": 100.0,
        "stop": 95.0,
        "tp1": 110.0,
        "tp2": 115.0,
        "tp3": 120.0,
    }
    record = SentSignalRecord.from_result(
        symbol="SOLUSDT",
        direction="BUY",
        risk=risk,
        confidence=92.0,
        timeframe="15",
        order_block=ob,
    )

    assert store.is_duplicate(record) is False
    store.record(record)
    assert store.is_duplicate(record) is True

    changed = SentSignalRecord.from_result(
        symbol="SOLUSDT",
        direction="SELL",
        risk=risk,
        confidence=91.0,
        timeframe="15",
        order_block=ob,
    )
    assert store.is_duplicate(changed) is False


def test_signal_store_different_order_block_not_duplicate(tmp_path: Path):
    store_path = tmp_path / "sent.json"
    store = SignalStore(store_path, window_minutes=30)
    risk = {
        "entry": 100.0,
        "stop": 95.0,
        "tp1": 110.0,
        "tp2": 115.0,
        "tp3": 120.0,
    }
    ob1 = {"bullish": {"low": 95.0, "high": 101.0}}
    ob2 = {"bullish": {"low": 94.0, "high": 100.0}}

    first = SentSignalRecord.from_result(
        symbol="SOLUSDT",
        direction="BUY",
        risk=risk,
        confidence=92.0,
        timeframe="15",
        order_block=ob1,
    )
    second = SentSignalRecord.from_result(
        symbol="SOLUSDT",
        direction="BUY",
        risk=risk,
        confidence=92.0,
        timeframe="15",
        order_block=ob2,
    )
    store.record(first)
    assert store.is_duplicate(second) is False


def test_signal_store_expires_after_window(tmp_path: Path):
    store_path = tmp_path / "sent.json"
    store = SignalStore(store_path, window_minutes=30)
    risk = {
        "entry": 1.2345,
        "stop": 1.2000,
        "tp1": 1.3000,
        "tp2": 1.3500,
        "tp3": 1.4000,
    }
    record = SentSignalRecord.from_result(
        symbol="XRPUSDT",
        direction="SELL",
        risk=risk,
        confidence=90.5,
        timeframe="15",
        order_block={"bearish": {"low": 1.22, "high": 1.25}},
    )
    record.sent_at = (
        datetime.now(timezone.utc) - timedelta(minutes=31)
    ).isoformat()
    store._records[record.symbol] = [record.__dict__]
    assert store.is_duplicate(record) is False


def test_signal_store_persists(tmp_path: Path):
    store_path = tmp_path / "sent.json"
    risk = {
        "entry": 1.2345,
        "stop": 1.2000,
        "tp1": 1.3000,
        "tp2": 1.3500,
        "tp3": 1.4000,
    }
    record = SentSignalRecord.from_result(
        symbol="XRPUSDT",
        direction="SELL",
        risk=risk,
        confidence=90.5,
        timeframe="15",
        order_block={"bearish": {"low": 1.22, "high": 1.25}},
    )

    store = SignalStore(store_path)
    store.record(record)

    reloaded = SignalStore(store_path)
    loaded = reloaded.recent("XRPUSDT")
    assert loaded
    assert loaded[0].fingerprint == record.fingerprint
    assert loaded[0].direction == "SELL"
