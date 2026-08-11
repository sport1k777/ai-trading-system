"""Tests for take-profit ladder mapping."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import pandas as pd

from app.risk.tp_mapper import map_take_profits


def _view(price=100.0):
    return pd.DataFrame({"high": [price + 1] * 40, "low": [price - 1] * 40, "close": [price] * 40})


@pytest.fixture
def buy_ctx():
    return SimpleNamespace(
        last={"poc": 107.0, "close": 100.0, "atr": 2.0},
        price=100.0,
        atr=2.0,
        swing_highs=[{"price": 108.0}, {"price": 112.0}, {"price": 118.0}],
        swing_lows=[{"price": 97.0}],
        order_block={"bullish": {"low": 99.0, "high": 100.5}, "bearish": None},
        liquidity={"type": "SELL_SIDE_SWEEP", "level": 98.0},
        fvg=None,
        htf_df=None,
        view=_view(100.0),
    )


def test_map_take_profits_orders_nearest_first(buy_ctx):
    entry, stop = 100.0, 98.0
    primary_tp = 104.4  # 2.2R — not forced to TP1

    with patch(
        "app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools",
        return_value={"buy_side_pools": [107.0, 110.0, 116.0], "sell_side_pools": []},
    ):
        result = map_take_profits(buy_ctx, "BUY", entry, stop, primary_tp)

    assert result is not None
    tp1, tp2, tp3 = result
    assert tp1 < tp2 < tp3
    assert len({tp1, tp2, tp3}) == 3


def test_map_take_profits_sell_orders_nearest_first():
    ctx = SimpleNamespace(
        last={"poc": 94.0, "close": 100.0, "atr": 2.0},
        price=100.0,
        atr=2.0,
        swing_highs=[{"price": 103.0}],
        swing_lows=[{"price": 94.0}, {"price": 90.0}, {"price": 88.0}],
        order_block={"bullish": None, "bearish": {"low": 99.5, "high": 100.5}},
        liquidity={"type": "BUY_SIDE_SWEEP", "level": 102.0},
        fvg=None,
        htf_df=None,
        view=_view(100.0),
    )
    entry, stop = 100.0, 102.0
    primary_tp = 95.6

    with patch(
        "app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools",
        return_value={"buy_side_pools": [], "sell_side_pools": [97.0, 94.0, 90.0]},
    ):
        result = map_take_profits(ctx, "SELL", entry, stop, primary_tp)

    assert result is not None
    tp1, tp2, tp3 = result
    assert tp3 < tp2 < tp1
    assert len({tp1, tp2, tp3}) == 3


def test_map_take_profits_no_longer_collapses_to_primary(buy_ctx):
    """Regression: old max(tp2, tp1) logic made all three targets identical."""
    entry, stop = 100.0, 98.0
    primary_tp = 104.4

    with patch(
        "app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools",
        return_value={"buy_side_pools": [107.0, 110.0, 116.0], "sell_side_pools": []},
    ):
        result = map_take_profits(buy_ctx, "BUY", entry, stop, primary_tp)

    assert result is not None
    tp1, tp2, tp3 = result
    assert tp1 != tp2 != tp3
