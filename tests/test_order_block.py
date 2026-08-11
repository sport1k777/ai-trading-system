"""Tests for order block nearest-zone selection."""

from __future__ import annotations

import pandas as pd

from app.analysis.order_block import OrderBlockAnalyzer
from app.analysis.poi_proximity import near_zone


def _make_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_order_block_picks_nearest_zone_in_lookback():
    rows = []
    for i in range(98):
        rows.append(
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
            }
        )

    # Older bullish OB near current price (~0.1% away).
    rows.append(
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 100.85,}
    )
    rows.extend(
        [
            {"open": 100.9, "high": 101.5, "low": 100.85, "close": 101.4},
            {"open": 101.4, "high": 101.6, "low": 101.2, "close": 101.5},
            {"open": 101.5, "high": 101.7, "low": 101.3, "close": 101.6},
            {"open": 101.6, "high": 101.8, "low": 101.4, "close": 101.7},
            {"open": 101.7, "high": 101.9, "low": 101.5, "close": 101.8},
            {"open": 101.8, "high": 102.0, "low": 101.6, "close": 101.9},
        ]
    )

    # Recent OB far from price (~2%).
    rows.append({"open": 104.0, "high": 104.2, "low": 103.8, "close": 103.85})
    rows.extend(
        [
            {"open": 103.9, "high": 104.5, "low": 103.85, "close": 104.4},
            {"open": 104.4, "high": 104.6, "low": 104.2, "close": 104.5},
            {"open": 104.5, "high": 104.7, "low": 104.3, "close": 104.6},
            {"open": 104.6, "high": 104.8, "low": 104.4, "close": 104.7},
            {"open": 104.7, "high": 104.9, "low": 104.5, "close": 104.8},
            {"open": 104.8, "high": 105.0, "low": 104.6, "close": 101.0},
        ]
    )

    df = _make_df(rows)
    result = OrderBlockAnalyzer.analyze(df)
    assert result is not None
    bullish = result["bullish"]
    assert bullish["low"] == 100.8
    assert near_zone(101.0, bullish["low"], bullish["high"], pct=0.003)


def test_order_block_returns_none_when_empty():
    df = pd.DataFrame(
        {
            "open": [10.0] * 25,
            "high": [11.0] * 25,
            "low": [9.0] * 25,
            "close": [10.5] * 25,
        }
    )
    assert OrderBlockAnalyzer.analyze(df) is None
