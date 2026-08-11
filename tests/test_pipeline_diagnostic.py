"""Tests for signal pipeline diagnostics."""

from __future__ import annotations

import pandas as pd

from app.diagnostics.pipeline_diagnostic import (
    diagnose_scan,
    diagnose_scan_block,
    format_diagnostic_block,
    format_gate_audit_block,
    log_decision_gate_audit,
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


def test_gate_audit_logs_every_decision_gate():
    result = _make_result(signal="WAIT", confidence=0)
    diag = diagnose_scan(result, timeframe="15", min_confidence=70)
    audit = format_gate_audit_block(result, diag, timeframe="15", min_confidence=70)

    assert "=== Decision Gate Audit | BTCUSDT" in audit
    assert "GATE | Trend | FAIL" in audit
    assert "GATE | HTF | FAIL" in audit
    assert "GATE | Volume |" in audit
    assert "GATE | Confluence BUY | FAIL" in audit
    assert "GATE | Engine pick_direction | FAIL" in audit
    assert "GATE | Telegram gate | FAIL" in audit
    assert "diagnostic confidence=" in audit


def test_log_decision_gate_audit_emits_lines(caplog):
    import logging

    caplog.set_level(logging.INFO)
    result = _make_result(signal="WAIT", confidence=0)
    diag = diagnose_scan(result, timeframe="15", min_confidence=70)
    audit_logger = logging.getLogger("test.gate_audit")

    log_decision_gate_audit(
        audit_logger,
        result,
        diag,
        timeframe="15",
        min_confidence=70,
    )

    joined = "\n".join(record.message for record in caplog.records)
    assert "GATE | BOS | FAIL" in joined
    assert "GATE | Engine signal | FAIL" in joined
