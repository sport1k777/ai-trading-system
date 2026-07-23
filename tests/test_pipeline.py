"""Tests for TradingPipeline risk passthrough."""

from __future__ import annotations

from app.pipeline import _risk_from_signal


def test_risk_from_signal_uses_engine_levels():
    signal = {
        "signal": "BUY",
        "entry": 100.0,
        "stop": 98.0,
        "tp": 104.0,
        "tp1": 104.0,
        "tp2": 106.0,
        "tp3": 108.0,
        "risk_reward": 2.0,
    }
    risk = _risk_from_signal(signal)
    assert risk is not None
    assert risk["entry"] == 100.0
    assert risk["stop"] == 98.0
    assert risk["tp1"] == 104.0
    assert risk["rr"] == 2.0


def test_risk_from_signal_returns_none_for_wait():
    assert _risk_from_signal({"signal": "WAIT"}) is None
    assert _risk_from_signal({"signal": "BUY"}) is None
