"""Tests for adaptive market regime detection."""

from __future__ import annotations

import pandas as pd

from app.analysis.market_regime import (
    MarketRegime,
    build_regime_profile,
    detect_market_regime,
    validate_regime_confirmations,
)
from app.analysis.pro.conditions import evaluate_all
from app.analysis.pro.models import ConditionResult


def _row(*, adx=30.0, atr_pct=1.0, close=110.0):
    return pd.Series(
        {
            "close": close,
            "open": close - 0.2,
            "ema50": 105.0,
            "adx": adx,
            "atr_pct": atr_pct,
            "rsi": 55.0,
            "volume_ratio": 1.2,
        }
    )


def test_detect_strong_trend():
    regime = detect_market_regime(
        last=_row(adx=32),
        trend="BULLISH",
        structure="UPTREND",
    )
    assert regime.trend_regime == "strong_trend"
    assert "Strong Trend" in regime.label


def test_detect_range_low_vol():
    regime = detect_market_regime(
        last=_row(adx=15, atr_pct=0.25),
        trend="SIDEWAYS",
        structure="RANGE",
    )
    assert regime.trend_regime == "range"
    assert regime.volatility_regime == "low"


def test_high_volatility_profile_wider_atr():
    regime = MarketRegime("weak_trend", "high", adx=22, atr_pct=4.5)
    profile = build_regime_profile(regime)
    assert profile.atr_max == 8.0
    assert profile.poi_tolerance_pct == 0.005


def test_strong_trend_regime_gate_requires_bos():
    regime = MarketRegime("strong_trend", "normal", adx=30, atr_pct=1.0)
    conditions = [
        ConditionResult("EMA Trend", "LONG", True, 12, "ok"),
        ConditionResult("ADX Trend", "LONG", True, 10, "ok"),
    ]
    ok, reason = validate_regime_confirmations(
        regime,
        "BUY",
        conditions,
        trend="BULLISH",
        htf_trend="BULLISH",
        bos="NO_BOS",
        choch="NO_CHOCH",
    )
    assert ok is False
    assert "BOS" in reason


def test_range_regime_accepts_choch_without_bos():
    regime = MarketRegime("range", "low", adx=12, atr_pct=0.2)
    conditions = evaluate_all(
        last=_row(adx=12, atr_pct=0.2),
        trend="SIDEWAYS",
        bos="NO_BOS",
        choch="BULLISH_CHOCH",
        liquidity=None,
        order_block=None,
        fvg=None,
        weights={
            "structure": 15,
            "fvg": 12,
            "order_block": 12,
            "liquidity": 15,
            "ema_trend": 12,
            "rsi": 10,
            "volume": 12,
            "atr": 12,
            "adx": 10,
            "htf": 12,
        },
    )
    ok, _ = validate_regime_confirmations(
        regime,
        "BUY",
        conditions,
        trend="SIDEWAYS",
        htf_trend="SIDEWAYS",
        bos="NO_BOS",
        choch="BULLISH_CHOCH",
    )
    assert ok is True
