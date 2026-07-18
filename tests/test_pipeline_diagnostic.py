"""Tests for signal pipeline diagnostics."""

from __future__ import annotations

import pandas as pd

from app.diagnostics.pipeline_diagnostic import (
    diagnose_scan,
    diagnose_scan_block,
    format_diagnostic_block,
)


def _make_result(*, symbol="BTCUSDT", signal="WAIT", confidence=0, reasons=None):
    df = pd.DataFrame(
        [{
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
            "ema20": 100.2,
            "ema50": 100.0,
            "ema200": 99.5,
            "rsi": 50.0,
            "macd_diff": 0.1,
            "atr": 1.0,
            "atr_pct": 1.0,
            "adx": 25.0,
            "bb_upper": 102.0,
            "bb_mid": 100.0,
            "bb_lower": 98.0,
            "volume_ratio": 1.0,
            "timestamp": "2026-07-10 12:00:00",
        }] * 60
    )

    class Result:
        pass

    r = Result()
    r.symbol = symbol
    r.df = df
    r.trend = "SIDEWAYS"
    r.structure = "RANGE"
    r.bos = "NO_BOS"
    r.choch = "NO_CHOCH"
    r.liquidity = None
    r.order_block = None
    r.fvg = None
    r.swing_highs = [{"price": 101.5}]
    r.swing_lows = [{"price": 99.0}]
    r.risk = None
    r.signal = {
        "signal": signal,
        "confidence": confidence,
        "buy_confidence": 10,
        "sell_confidence": 12,
        "reasons": reasons or ["Confluence insufficient"],
        "confluence_hits": {"long": 1, "short": 1},
    }
    return r


def test_diagnostic_reports_failed_checks():
    diag = diagnose_scan(_make_result(), timeframe="15", min_confidence=90)
    block = format_diagnostic_block(diag)

    assert "BTCUSDT" in block
    assert "HTF bias: FAIL" in block
    assert "Rejected because" in block
    assert diag.engine_signal == "WAIT"
    assert diag.would_alert is False


def test_diagnostic_detects_telegram_gate():
    result = _make_result(signal="BUY", confidence=82, reasons=["ok"])
    result.risk = {"entry": 100, "stop": 99, "tp1": 102, "tp2": 103, "tp3": 104, "rr": 2.0}

    diag = diagnose_scan(result, timeframe="15", min_confidence=90)

    assert diag.telegram_blocked is True
    assert "Telegram confidence gate" in diag.rejection_reason


def test_diagnose_scan_block_import_and_format():
    result = _make_result(signal="WAIT", confidence=0)
    block = diagnose_scan_block(result, timeframe="15", min_confidence=70)
    assert "BTCUSDT" in block
    assert "Rejected because" in block
