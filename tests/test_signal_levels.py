"""Tests for signal level finalization and validation."""

from __future__ import annotations

import pytest

from app.pipeline import _risk_from_signal
from app.risk.signal_levels import (
    compute_rr,
    finalize_risk_levels,
    finalize_take_profits,
    normalize_risk_dict,
    validate_signal_risk,
)
from app.risk.risk_manager import RiskManager


def test_compute_rr_matches_percentages():
    entry, stop, tp1 = 100.0, 98.0, 104.0
    rr = compute_rr(entry, stop, tp1)
    risk_pct = abs(entry - stop) / entry * 100
    reward_pct = abs(tp1 - entry) / entry * 100
    assert rr == pytest.approx(reward_pct / risk_pct, rel=1e-6)
    assert rr == 2.0


def test_finalize_take_profits_never_equals_entry():
    tp1, tp2, tp3 = finalize_take_profits("BUY", 100.0, 98.0, 100.0, 100.0, 100.0)
    assert tp1 != 100.0
    assert tp1 != tp2 != tp3
    assert tp1 < tp2 < tp3


def test_finalize_take_profits_sell_distinct():
    tp1, tp2, tp3 = finalize_take_profits("SELL", 100.0, 102.0, 100.0, 100.0, 100.0)
    assert tp1 != 100.0
    assert tp1 != tp2 != tp3
    assert tp3 < tp2 < tp1


def test_finalize_risk_levels_rr_matches_tp1():
    risk = finalize_risk_levels("BUY", 100.0, 98.0, 101.5, 103.0, 104.0)
    assert risk["rr"] == compute_rr(risk["entry"], risk["stop"], risk["tp1"])
    assert len({risk["tp1"], risk["tp2"], risk["tp3"]}) == 3


def test_validate_rejects_tp1_equal_entry():
    risk = {
        "entry": 100.0,
        "stop": 98.0,
        "tp1": 100.0,
        "tp2": 102.0,
        "tp3": 104.0,
        "rr": 0.0,
    }
    ok, reason = validate_signal_risk("BUY", risk)
    assert ok is False
    assert "TP1 equals entry" in reason


def test_validate_rejects_duplicate_tps():
    risk = {
        "entry": 100.0,
        "stop": 98.0,
        "tp1": 104.0,
        "tp2": 104.0,
        "tp3": 106.0,
        "rr": 2.0,
    }
    ok, reason = validate_signal_risk("BUY", risk)
    assert ok is False
    assert "Duplicate" in reason


def test_validate_rejects_rr_mismatch():
    risk = {
        "entry": 100.0,
        "stop": 98.0,
        "tp1": 104.0,
        "tp2": 106.0,
        "tp3": 108.0,
        "rr": 3.0,
    }
    ok, reason = validate_signal_risk("BUY", risk)
    assert ok is False
    assert "R:R mismatch" in reason


def test_risk_manager_returns_distinct_tps():
    risk = RiskManager.calculate(100.0, 1.0, "BUY", swing_low=97.0, setup_type="pro_signal")
    assert risk is not None
    assert risk["tp1"] != risk["tp2"] != risk["tp3"]
    ok, _ = validate_signal_risk("BUY", risk)
    assert ok is True


def test_risk_from_signal_normalizes_invalid_rr():
    signal = {
        "signal": "BUY",
        "entry": 100.0,
        "stop": 98.0,
        "tp1": 104.0,
        "tp2": 106.0,
        "tp3": 108.0,
        "risk_reward": 2.0,
    }
    risk = _risk_from_signal(signal)
    assert risk is not None
    assert risk["rr"] == 2.0


def test_risk_from_signal_normalizes_invalid_duplicate_tps():
    signal = {
        "signal": "BUY",
        "entry": 100.0,
        "stop": 98.0,
        "tp1": 100.0,
        "tp2": 100.0,
        "tp3": 100.0,
        "risk_reward": 2.0,
    }
    risk = _risk_from_signal(signal)
    assert risk is None


def test_normalize_risk_dict_rejects_duplicate_tps():
    raw = {
        "entry": 76.6,
        "stop": 73.0,
        "tp1": 80.6,
        "tp2": 80.6,
        "tp3": 80.6,
        "rr": 1.1,
    }
    risk = normalize_risk_dict("BUY", raw)
    assert risk is None
