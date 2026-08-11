"""Tests for persistent BOS/CHOCH/HTF structure detection."""

from __future__ import annotations

import pandas as pd

from app.analysis.bos import BOSAnalyzer
from app.analysis.structure_persistence import (
    _bos_at_bar,
    analyze_bos_persistent,
    resolve_htf_trend,
    resolve_ltf_trend,
)


def _flat_df(rows: int = 40) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=rows, freq="15min"),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
            "ema20": 100.0,
            "ema50": 100.0,
            "ema200": 100.0,
            "ema20_slope": 0.0,
        }
    )


def _make_swing_high_break(df: pd.DataFrame, *, swing_bar: int, break_bar: int) -> None:
    for i in range(len(df)):
        df.loc[i, ["open", "high", "low", "close"]] = [100.0, 101.0, 99.0, 100.0]
    for offset in range(-3, 4):
        idx = swing_bar + offset
        if 0 <= idx < len(df):
            df.loc[idx, "high"] = 101.0
            df.loc[idx, "low"] = 99.0
    df.loc[swing_bar, "high"] = 103.0
    df.loc[break_bar, "close"] = 104.0
    df.loc[break_bar, "high"] = 104.5
    for idx in range(break_bar + 1, len(df)):
        df.loc[idx, "close"] = 102.0
        df.loc[idx, "high"] = 102.5
        df.loc[idx, "low"] = 101.5


def test_bos_persists_after_pullback():
    df = _flat_df(40)
    _make_swing_high_break(df, swing_bar=20, break_bar=32)

    assert _bos_at_bar(df.iloc[:33]) == "BULLISH_BOS"
    assert _bos_at_bar(df) is None
    assert analyze_bos_persistent(df, lookback=12) == "BULLISH_BOS"
    assert BOSAnalyzer.analyze(df, lookback=12) == "BULLISH_BOS"


def test_bos_no_lookahead():
    df = _flat_df(40)
    _make_swing_high_break(df, swing_bar=20, break_bar=32)

    assert analyze_bos_persistent(df.iloc[:33], lookback=12) == "BULLISH_BOS"
    assert analyze_bos_persistent(df.iloc[:31], lookback=12) == "NO_BOS"


def test_resolve_ltf_trend_from_structure():
    df = _flat_df(210)
    assert resolve_ltf_trend(df, "UPTREND") == "BULLISH"
    assert resolve_ltf_trend(df, "DOWNTREND") == "BEARISH"
    assert resolve_ltf_trend(df, "RANGE") == "SIDEWAYS"


def test_resolve_htf_trend_persists_until_invalidation():
    df = _flat_df(60)
    for i in range(60):
        close = 100.0 + i * 0.15
        df.loc[i, "close"] = close
        df.loc[i, "open"] = close - 0.1
        df.loc[i, "high"] = close + 0.3
        df.loc[i, "low"] = close - 0.3
        df.loc[i, "ema20"] = close - 0.2
        df.loc[i, "ema50"] = close - 0.5
        df.loc[i, "ema200"] = close - 1.0
    # Soft pullback on final bars without breaking structure
    df.loc[58:, "close"] = df.loc[57, "close"]
    df.loc[58:, "low"] = df.loc[57, "close"] - 0.4

    trend = resolve_htf_trend(df, lookback=12)
    assert trend == "BULLISH"
