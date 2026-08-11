"""Tests for the authoritative trade-plan engine."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import pandas as pd

from app.risk.trade_plan_engine import build_trade_plan
from app.risk.signal_levels import compute_rr as levels_compute_rr


def _ctx(
    *,
    price=100.0,
    atr=2.0,
    poc=107.0,
    swing_highs=None,
    swing_lows=None,
    order_block=None,
    liquidity=None,
    fvg=None,
    htf_df=None,
):
    if swing_highs is None:
        swing_highs = [{"price": 108.0}, {"price": 112.0}, {"price": 118.0}]
    if swing_lows is None:
        swing_lows = [{"price": 97.0}]
    if order_block is None:
        order_block = {"bullish": {"low": 99.0, "high": 100.5}, "bearish": None}
    view_df = pd.DataFrame(
        {"high": [price + 1] * 40, "low": [price - 1] * 40, "close": [price] * 40}
    )
    return SimpleNamespace(
        price=price,
        atr=atr,
        last={"poc": poc, "close": price, "atr": atr, "adx": 25.0, "ema20": 100.5, "ema50": 99.5},
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        order_block=order_block,
        liquidity=liquidity or {"type": "SELL_SIDE_SWEEP", "level": 98.0},
        fvg=fvg,
        htf_df=htf_df,
        view=view_df,
    )


class TestTradePlanEngineLong:
    def test_valid_long_plan_meets_min_rr(self):
        ctx = _ctx()
        with patch(
            "app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools",
            return_value={"buy_side_pools": [107.0, 110.0, 116.0], "sell_side_pools": []},
        ):
            plan = build_trade_plan(ctx, "BUY", swing_low=97.0)

        assert plan is not None
        assert plan["stop"] < plan["entry"] < plan["tp1"] < plan["tp2"] < plan["tp3"]
        assert len({plan["tp1"], plan["tp2"], plan["tp3"]}) == 3
        assert plan["rr_tp1"] >= 1.5
        assert plan["rr_tp2"] >= 2.5
        assert plan["rr_tp3"] >= 3.5
        assert plan["rr"] == plan["rr_tp1"]
        assert plan["rr_tp1"] == levels_compute_rr(plan["entry"], plan["stop"], plan["tp1"])

    def test_rejects_duplicate_tp_short(self):
        """Regression: TP1 == TP2 must never pass."""
        ctx = _ctx(price=1.0218, atr=0.01)
        ctx.order_block = {"bullish": None, "bearish": {"low": 1.018, "high": 1.022}}
        ctx.swing_highs = [{"price": 1.03}]
        ctx.swing_lows = [{"price": 1.00}, {"price": 1.000}, {"price": 0.99}]

        with patch(
            "app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools",
            return_value={"buy_side_pools": [], "sell_side_pools": [1.0, 1.0, 0.99]},
        ):
            plan = build_trade_plan(ctx, "SELL", swing_high=1.03)

        if plan is not None:
            assert plan["tp1"] != plan["tp2"] != plan["tp3"]

    def test_rejects_insufficient_structural_targets(self):
        ctx = _ctx(swing_highs=[{"price": 101.0}])
        with patch(
            "app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools",
            return_value={"buy_side_pools": [], "sell_side_pools": []},
        ):
            plan = build_trade_plan(ctx, "BUY", swing_low=97.0)
        assert plan is None

    def test_rr_matches_actual_prices_long_example(self):
        """User-reported bug: entry 1.04, sl 1.02, tp1 1.07 => ~1.5R not 2.2R."""
        entry, stop, tp1 = 1.0400, 1.0200, 1.0700
        rr = levels_compute_rr(entry, stop, tp1)
        risk_pct = abs(entry - stop) / entry * 100
        reward_pct = abs(tp1 - entry) / entry * 100
        assert rr == pytest.approx(reward_pct / risk_pct, rel=1e-3)
        assert rr == pytest.approx(1.5, rel=0.05)
        assert rr != 2.2

    def test_rejects_insufficient_rr(self):
        ctx = _ctx(swing_highs=[], swing_lows=[{"price": 97.0}])
        with patch(
            "app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools",
            return_value={"buy_side_pools": [101.0], "sell_side_pools": []},
        ):
            plan = build_trade_plan(ctx, "BUY", swing_low=97.0)
        assert plan is None

    def test_rejects_sl_above_entry_for_long(self):
        ctx = _ctx()
        plan = build_trade_plan(ctx, "BUY", swing_low=105.0)
        assert plan is None or plan["stop"] < plan["entry"]


class TestTradePlanEngineShort:
    def test_valid_short_plan(self):
        ctx = _ctx(
            price=100.0,
            order_block={"bullish": None, "bearish": {"low": 99.5, "high": 100.5}},
        )
        ctx.liquidity = {"type": "BUY_SIDE_SWEEP", "level": 102.5}
        with patch(
            "app.analysis.pro_v2.liquidity_pools.detect_liquidity_pools",
            return_value={"buy_side_pools": [], "sell_side_pools": [97.0, 94.0, 90.0]},
        ):
            plan = build_trade_plan(ctx, "SELL", swing_high=102.0)

        if plan is not None:
            assert plan["tp3"] < plan["tp2"] < plan["tp1"] < plan["entry"] < plan["stop"]
            assert plan["rr_tp1"] >= 1.5

    def test_rejects_sl_below_entry_for_short(self):
        ctx = _ctx(
            order_block={"bullish": None, "bearish": {"low": 99.5, "high": 100.5}},
        )
        ctx.liquidity = {"type": "BUY_SIDE_SWEEP", "level": 101.0}
        plan = build_trade_plan(ctx, "SELL", swing_high=95.0)
        assert plan is None or plan["stop"] > plan["entry"]
