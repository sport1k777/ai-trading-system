"""Comprehensive signal validation tests — 10k random + replay coverage."""

from __future__ import annotations

import random
from types import SimpleNamespace

import pandas as pd
import pytest

from app.analysis.pro_v2.grader import GRADE_BASE
from app.risk.signal_levels import finalize_risk_levels, sync_risk_rr
from app.telegram.formatter import format_live_signal_message
from app.validation.signal_validator import ValidationResult, validate_signal


def _make_result(
    *,
    direction: str = "BUY",
    entry: float = 100.0,
    stop: float = 98.0,
    tp1: float = 103.0,
    tp2: float = 105.0,
    tp3: float = 107.0,
    confidence: float = 88.0,
    grade: str = "A",
    price: float = 100.0,
    htf_bias: str = "HTF bullish bias (UPTREND, BULLISH_BOS)",
    structure: str = "UPTREND",
    trend: str = "BULLISH",
    counter_trend_label: str | None = None,
    finalize: bool = True,
) -> SimpleNamespace:
    ob_low = entry * 0.995
    ob_high = entry * 1.005
    reasons = ["Test signal"]
    if counter_trend_label:
        reasons.append(counter_trend_label)

    if finalize:
        risk = sync_risk_rr(finalize_risk_levels(direction, entry, stop, tp1, tp2, tp3))
    else:
        risk = {
            "entry": entry,
            "stop": stop,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "rr": 1.0,
        }

    if direction == "BUY":
        order_block = {"bullish": {"low": ob_low, "high": ob_high}, "bearish": None}
        liquidity = {"type": "SELL_SIDE_SWEEP", "level": stop}
        ema20, ema50, rsi = entry * 1.002, entry * 0.998, 55.0
    else:
        order_block = {"bullish": None, "bearish": {"low": ob_low, "high": ob_high}}
        liquidity = {"type": "BUY_SIDE_SWEEP", "level": stop}
        ema20, ema50, rsi = entry * 0.998, entry * 1.002, 45.0

    indicator_row = {
        "close": price,
        "timestamp": "2026-07-31",
        "atr": max(abs(entry - stop) * 0.5, 0.01),
        "adx": 25.0,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "volume_ratio": 1.2,
    }

    return SimpleNamespace(
        symbol="BTCUSDT",
        df=pd.DataFrame([indicator_row]),
        signal={
            "signal": direction,
            "confidence": confidence,
            "grade": grade,
            "htf_bias": htf_bias,
            "setup_type": "pro_v2_signal",
            "reasons": reasons,
            "explanation": "; ".join(reasons),
            "orderblock": order_block,
            "bos": "BULLISH_BOS" if direction == "BUY" else "BEARISH_BOS",
            "choch": "NO_CHOCH",
            "liquidity": liquidity,
        },
        risk=risk,
        trend=trend,
        structure=structure,
        bos="BULLISH_BOS" if direction == "BUY" else "BEARISH_BOS",
        choch="NO_CHOCH",
        liquidity=liquidity,
        order_block=order_block,
        fvg=None,
        swing_highs=[{"price": tp3}],
        swing_lows=[{"price": stop}],
        price=price,
    )


class TestValidateSignalUnit:
    def test_valid_buy_passes(self):
        result = _make_result()
        v = validate_signal(result, min_confidence=70)
        assert v.ok is True

    def test_missing_entry_rejected(self):
        result = _make_result()
        result.risk["entry"] = None
        v = validate_signal(result, min_confidence=70)
        assert v.ok is False

    def test_tp1_equals_entry_rejected(self):
        result = _make_result(finalize=False)
        result.risk["tp1"] = result.risk["entry"]
        v = validate_signal(result, min_confidence=70)
        assert v.ok is False

    def test_duplicate_tp_rejected(self):
        result = _make_result(finalize=False)
        result.risk["tp2"] = result.risk["tp1"]
        v = validate_signal(result, min_confidence=70)
        assert v.ok is False

    def test_risk_too_low_rejected(self):
        result = _make_result(entry=100.0, stop=99.9, tp1=100.5, tp2=100.8, tp3=101.0)
        result.risk = finalize_risk_levels("BUY", 100.0, 99.9, 100.5, 100.8, 101.0)
        v = validate_signal(result, min_confidence=70)
        assert v.ok is False
        assert any("Risk" in e for e in v.errors)

    def test_risk_too_high_rejected(self):
        result = _make_result(entry=100.0, stop=90.0, tp1=110.0, tp2=115.0, tp3=120.0)
        result.risk = finalize_risk_levels("BUY", 100.0, 90.0, 110.0, 115.0, 120.0)
        v = validate_signal(result, min_confidence=70)
        assert v.ok is False

    def test_counter_trend_sell_without_label_rejected(self):
        result = _make_result(
            direction="SELL",
            entry=100.0,
            stop=102.0,
            tp1=98.0,
            tp2=96.0,
            tp3=94.0,
            htf_bias="HTF bullish bias (UPTREND, BULLISH_BOS)",
            structure="UPTREND",
            trend="BULLISH",
        )
        v = validate_signal(result, min_confidence=70)
        assert v.ok is False

    def test_counter_trend_sell_with_label_passes(self):
        result = _make_result(
            direction="SELL",
            entry=100.0,
            stop=102.0,
            tp1=97.0,
            tp2=95.0,
            tp3=93.0,
            htf_bias="HTF bullish bias (UPTREND, BULLISH_BOS)",
            structure="UPTREND",
            trend="BULLISH",
            counter_trend_label="Counter Trend Sell",
        )
        v = validate_signal(result, min_confidence=70)
        assert v.ok is True
        assert v.counter_trend is True

    def test_grade_confidence_mismatch_rejected(self):
        result = _make_result(confidence=55.0, grade="A")
        v = validate_signal(result, min_confidence=50)
        assert v.ok is False

    def test_hardcoded_rr_rejected(self):
        result = _make_result()
        result.risk["rr"] = 2.2
        v = validate_signal(result, min_confidence=70)
        assert v.ok is False
        assert any("R:R" in e for e in v.errors)

    def test_price_drift_rejected(self):
        result = _make_result(entry=100.0, price=100.5)
        v = validate_signal(result, min_confidence=70, price_drift_max_pct=0.25)
        assert v.ok is False
        assert any("Price drift" in e for e in v.errors)

    def test_missing_bos_rejected(self):
        result = _make_result()
        result.bos = "NO_BOS"
        result.signal["bos"] = "NO_BOS"
        v = validate_signal(result, min_confidence=70)
        assert v.ok is False
        assert any("BOS" in e for e in v.errors)


def _random_invalid_signal(rng: random.Random) -> SimpleNamespace:
    direction = rng.choice(["BUY", "SELL"])
    entry = rng.uniform(10, 500)
    flaw = rng.randint(0, 12)

    if direction == "BUY":
        stop = entry - rng.uniform(0.01, entry * 0.05)
        tp1 = entry + rng.uniform(0.5, entry * 0.05)
        tp2 = tp1 + rng.uniform(0.5, entry * 0.03)
        tp3 = tp2 + rng.uniform(0.5, entry * 0.03)
    else:
        stop = entry + rng.uniform(0.01, entry * 0.05)
        tp1 = entry - rng.uniform(0.5, entry * 0.05)
        tp2 = tp1 - rng.uniform(0.5, entry * 0.03)
        tp3 = tp2 - rng.uniform(0.5, entry * 0.03)

    if flaw == 0:
        entry = -entry
    elif flaw == 1:
        tp1 = entry
    elif flaw == 2:
        tp2 = tp1
    elif flaw == 3:
        stop = entry + (1 if direction == "BUY" else -1)
    elif flaw == 4:
        stop = entry - entry * 0.1 if direction == "BUY" else entry + entry * 0.1
    elif flaw == 5:
        entry = entry * 10  # far from price
    elif flaw == 6:
        tp3 = tp1
    elif flaw == 7:
        stop = entry  # zero risk

    ob_low = entry * 0.995 if flaw != 8 else entry * 1.05
    ob_high = entry * 1.005 if flaw != 8 else entry * 1.06

    grade = rng.choice(list(GRADE_BASE.keys()))
    confidence = GRADE_BASE[grade] + rng.uniform(-3, 3)
    if flaw == 10:
        confidence = 150
    if flaw == 11:
        confidence = GRADE_BASE["C"] - 10
        grade = "A"
    if flaw == 12:
        grade = "C"
        confidence = GRADE_BASE["A"] + 5

    htf = "HTF bullish bias" if direction == "SELL" and flaw == 12 else "HTF neutral"

    result = _make_result(
        direction=direction,
        entry=entry,
        stop=stop,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        confidence=confidence,
        grade=grade,
        price=entry if flaw != 5 else entry / 10,
        htf_bias=htf,
        finalize=False,
    )
    result.risk = {
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "rr": abs(tp1 - entry) / max(abs(entry - stop), 1e-9),
    }

    if flaw == 0:
        result.risk["entry"] = -abs(entry)
    elif flaw == 1:
        result.risk["tp1"] = entry
    elif flaw == 2:
        result.risk["tp2"] = result.risk["tp1"]
    elif flaw == 3:
        result.risk["stop"] = entry + (1 if direction == "BUY" else -1)
    elif flaw == 6:
        result.risk["tp3"] = result.risk["tp1"]
    elif flaw == 7:
        result.risk["stop"] = entry
    elif flaw == 8:
        result.order_block = {"bullish" if direction == "BUY" else "bearish": {"low": ob_low, "high": ob_high}}
        result.signal["orderblock"] = result.order_block
    elif flaw == 9:
        result.risk["rr"] = float(result.risk.get("rr", 1)) + 5

    if direction == "BUY":
        result.order_block = {"bullish": {"low": ob_low, "high": ob_high}, "bearish": None}
    else:
        result.order_block = {"bullish": None, "bearish": {"low": ob_low, "high": ob_high}}
    result.signal["orderblock"] = result.order_block

    return result


@pytest.mark.parametrize("seed", range(10))
def test_random_invalid_signals_rejected(seed: int):
    rng = random.Random(seed)
    rejected = 0
    for _ in range(1000):
        result = _random_invalid_signal(rng)
        v = validate_signal(result, min_confidence=50)
        if not v.ok:
            rejected += 1
    assert rejected >= 950, f"Expected most random flawed signals rejected, got {rejected}/1000"


def test_ten_thousand_random_validation():
    rng = random.Random(42)
    rejected = 0
    for i in range(10000):
        result = _random_invalid_signal(rng)
        v = validate_signal(result, min_confidence=50)
        if not v.ok:
            rejected += 1
    assert rejected >= 9800, f"10k random: rejected {rejected}/10000"


def test_replay_telegram_messages_pass_validation():
    """1000 synthetic replay-grade signals — formatter only when validation passes."""
    rng = random.Random(7)
    sent = 0
    for i in range(1000):
        direction = rng.choice(["BUY", "SELL"])
        entry = rng.uniform(50, 300)
        risk_pct = rng.uniform(0.4, 2.5) / 100.0
        if direction == "BUY":
            stop = entry * (1 - risk_pct)
            tp1 = entry * (1 + risk_pct * rng.uniform(1.5, 2.5))
            tp2 = entry * (1 + risk_pct * rng.uniform(2.5, 3.5))
            tp3 = entry * (1 + risk_pct * rng.uniform(3.5, 5.0))
        else:
            stop = entry * (1 + risk_pct)
            tp1 = entry * (1 - risk_pct * rng.uniform(1.5, 2.5))
            tp2 = entry * (1 - risk_pct * rng.uniform(2.5, 3.5))
            tp3 = entry * (1 - risk_pct * rng.uniform(3.5, 5.0))

        htf = (
            "HTF bullish bias (UPTREND, BULLISH_BOS)"
            if direction == "BUY"
            else "HTF bearish bias (DOWNTREND, BEARISH_BOS)"
        )
        structure = "UPTREND" if direction == "BUY" else "DOWNTREND"
        trend = "BULLISH" if direction == "BUY" else "BEARISH"

        result = _make_result(
            direction=direction,
            entry=entry,
            stop=stop,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            price=entry,
            confidence=88.0,
            grade="A",
            htf_bias=htf,
            structure=structure,
            trend=trend,
        )

        v = validate_signal(result, min_confidence=70)
        assert v.ok, v.errors
        msg = format_live_signal_message(result, min_confidence=70)
        assert msg is not None
        sent += 1

    assert sent == 1000
