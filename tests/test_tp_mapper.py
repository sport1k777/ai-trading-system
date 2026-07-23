"""Tests for take-profit ladder mapping."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.risk.tp_mapper import map_take_profits


@pytest.fixture
def buy_ctx():
    return SimpleNamespace(
        last={"poc": 101.5},
        swing_highs=[{"price": 106.0}],
        swing_lows=[{"price": 97.0}],
    )


def test_map_take_profits_orders_nearest_first(buy_ctx):
    entry, stop = 100.0, 98.0
    primary_tp = 104.4  # 2.2R

    with patch("app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools", return_value={"buy_side_pools": [103.0, 105.5], "sell_side_pools": []}):
        tp1, tp2, tp3 = map_take_profits(buy_ctx, "BUY", entry, stop, primary_tp)

    assert tp1 < tp2 < tp3
    assert tp1 == pytest.approx(101.5)
    assert tp2 == pytest.approx(103.0)
    assert tp3 == pytest.approx(104.0)
    assert len({tp1, tp2, tp3}) == 3


def test_map_take_profits_sell_orders_nearest_first():
    ctx = SimpleNamespace(
        last={"poc": 98.5},
        swing_highs=[{"price": 103.0}],
        swing_lows=[{"price": 94.0}],
    )
    entry, stop = 100.0, 102.0
    primary_tp = 95.6  # 2.2R short

    with patch("app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools", return_value={"buy_side_pools": [], "sell_side_pools": [97.0, 94.5]}):
        tp1, tp2, tp3 = map_take_profits(ctx, "SELL", entry, stop, primary_tp)

    assert tp3 < tp2 < tp1
    assert tp1 == pytest.approx(98.5)
    assert tp2 == pytest.approx(97.0)
    assert tp3 == pytest.approx(96.0)
    assert len({tp1, tp2, tp3}) == 3


def test_map_take_profits_no_longer_collapses_to_primary(buy_ctx):
    """Regression: old max(tp2, tp1) logic made all three targets identical."""
    entry, stop = 100.0, 98.0
    primary_tp = 104.4

    with patch("app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools", return_value={"buy_side_pools": [], "sell_side_pools": []}):
        tp1, tp2, tp3 = map_take_profits(buy_ctx, "BUY", entry, stop, primary_tp)

    assert tp1 != tp2 != tp3
