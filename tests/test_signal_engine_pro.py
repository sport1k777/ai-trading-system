"""Tests for Signal Engine PRO confluence system."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from app.analysis.pro.conditions import (
    evaluate_ema_trend,
    evaluate_fvg,
    evaluate_liquidity,
    evaluate_order_block,
    evaluate_rsi,
    evaluate_structure,
    evaluate_volume,
    is_volatility_tradeable,
)
from app.analysis.pro.confluence import pick_direction, score_confluence
from app.analysis.pro.engine import SignalEnginePro
from app.analysis.signal_generator import SignalGenerator
from app.indicators.signals import SignalIndicators


def _indicator_row(
    *,
    close: float = 110.0,
    open_: float = 109.0,
    rsi: float = 55.0,
    volume_ratio: float = 1.3,
    atr_pct: float = 0.8,
) -> pd.Series:
    return pd.Series(
        {
            "close": close,
            "open": open_,
            "ema20": 108.0,
            "ema50": 105.0,
            "ema200": 100.0,
            "rsi": rsi,
            "volume_ratio": volume_ratio,
            "atr_pct": atr_pct,
            "atr": 1.0,
            "adx": 28.0,
            "macd_diff": 0.1,
            "bb_upper": 115.0,
            "bb_mid": 110.0,
            "bb_lower": 105.0,
        }
    )


class TestConditions:
    def test_structure_bullish_bos(self):
        result = evaluate_structure("BULLISH_BOS", "NO_CHOCH", weight=15)
        assert result.aligned is True
        assert result.direction == "LONG"
        assert "BOS" in result.reason

    def test_structure_bearish_choch(self):
        result = evaluate_structure("NO_BOS", "BEARISH_CHOCH", weight=15)
        assert result.aligned is True
        assert result.direction == "SHORT"

    def test_fvg_bullish_zone(self):
        fvg = {"type": "BULLISH", "top": 111.0, "bottom": 109.0}
        result = evaluate_fvg(fvg, 110.0, weight=12)
        assert result.aligned is True
        assert result.direction == "LONG"

    def test_order_block_bullish_zone(self):
        ob = {"bullish": {"low": 109.0, "high": 111.0}, "bearish": None}
        result = evaluate_order_block(ob, 110.0, weight=12)
        assert result.aligned is True
        assert result.direction == "LONG"

    def test_fvg_bullish_within_proximity(self):
        fvg = {"type": "BULLISH", "top": 111.0, "bottom": 109.0}
        result = evaluate_fvg(fvg, 108.72, weight=12)
        assert result.aligned is True
        assert "0.3%" in result.reason

    def test_order_block_bullish_within_proximity(self):
        ob = {"bullish": {"low": 109.0, "high": 111.0}, "bearish": None}
        result = evaluate_order_block(ob, 108.72, weight=12)
        assert result.aligned is True
        assert "0.3%" in result.reason

    def test_fvg_outside_proximity(self):
        fvg = {"type": "BULLISH", "top": 111.0, "bottom": 109.0}
        result = evaluate_fvg(fvg, 108.0, weight=12)
        assert result.aligned is False

    def test_liquidity_sell_side_sweep_long(self):
        liq = {"type": "SELL_SIDE_SWEEP", "level": 100.0, "price": 100.5}
        result = evaluate_liquidity(liq, weight=15)
        assert result.direction == "LONG"

    def test_ema_trend_bullish(self):
        row = _indicator_row(close=110.0)
        result = evaluate_ema_trend("BULLISH", row, weight=12)
        assert result.aligned is True
        assert result.direction == "LONG"

    def test_rsi_long_zone(self):
        result = evaluate_rsi(_indicator_row(rsi=58.0), weight=10)
        assert result.aligned is True
        assert result.direction == "LONG"

    def test_volume_bullish_expansion(self):
        result = evaluate_volume(_indicator_row(open_=109.0, close=110.0, volume_ratio=1.4), weight=12)
        assert result.aligned is True
        assert result.direction == "LONG"

    def test_volatility_gate(self):
        ok, _ = is_volatility_tradeable(_indicator_row(atr_pct=0.8))
        assert ok is True
        ok, reason = is_volatility_tradeable(_indicator_row(atr_pct=0.05))
        assert ok is False
        assert "range" in reason.lower()


class TestConfluence:
    def test_score_confluence_counts_hits(self):
        row = _indicator_row()
        score = score_confluence(
            last=row,
            trend="BULLISH",
            bos="BULLISH_BOS",
            choch="NO_CHOCH",
            liquidity={"type": "SELL_SIDE_SWEEP", "level": 100.0, "price": 100.5},
            order_block={"bullish": {"low": 109.0, "high": 111.0}, "bearish": None},
            fvg={"type": "BULLISH", "top": 111.0, "bottom": 109.0},
        )
        assert score.long_hits >= 5
        assert score.long_score > score.short_score

    def test_pick_direction_long(self):
        row = _indicator_row()
        score = score_confluence(
            last=row,
            trend="BULLISH",
            bos="BULLISH_BOS",
            choch="NO_CHOCH",
            liquidity={"type": "SELL_SIDE_SWEEP", "level": 100.0, "price": 100.5},
            order_block={"bullish": {"low": 109.0, "high": 111.0}, "bearish": None},
            fvg={"type": "BULLISH", "top": 111.0, "bottom": 109.0},
        )
        direction, confidence, reasons = pick_direction(
            score,
            min_conditions=5,
            min_confidence=60,
            min_gap=5,
        )
        assert direction == "BUY"
        assert confidence >= 60
        assert len(reasons) >= 5

    def test_pick_direction_none_when_weak(self):
        row = _indicator_row(rsi=50.0, volume_ratio=0.8)
        score = score_confluence(
            last=row,
            trend="SIDEWAYS",
            bos="NO_BOS",
            choch="NO_CHOCH",
            liquidity=None,
            order_block=None,
            fvg=None,
        )
        direction, _, reasons = pick_direction(
            score,
            min_conditions=5,
            min_confidence=65,
            min_gap=10,
        )
        assert direction is None
        assert reasons == []


class TestSignalEnginePro:
    def test_wait_on_short_data(self):
        df = pd.DataFrame({"open": [1.0] * 10, "high": [1.1] * 10, "low": [0.9] * 10, "close": [1.0] * 10})
        result = SignalEnginePro.generate(df)
        assert result["signal"] == "WAIT"

    def test_generates_long_signal_with_full_confluence(self, sample_ohlcv):
        df = SignalIndicators.calculate(sample_ohlcv)
        last_idx = len(df) - 1
        df.loc[last_idx, "close"] = 130.0
        df.loc[last_idx, "open"] = 128.5
        df.loc[last_idx, "high"] = 131.0
        df.loc[last_idx, "low"] = 128.0
        df.loc[last_idx, "rsi"] = 58.0
        df.loc[last_idx, "volume_ratio"] = 1.5
        df.loc[last_idx, "atr_pct"] = 0.9

        with (
            patch("app.analysis.pro.engine.TrendAnalyzer.detect_trend", return_value="BULLISH"),
            patch("app.analysis.pro.engine.BOSAnalyzer.analyze", return_value="BULLISH_BOS"),
            patch("app.analysis.pro.engine.CHOCHAnalyzer.analyze", return_value="NO_CHOCH"),
            patch(
                "app.analysis.pro.engine.LiquidityAnalyzer.analyze",
                return_value={"type": "SELL_SIDE_SWEEP", "level": 120.0, "price": 120.5},
            ),
            patch(
                "app.analysis.pro.engine.OrderBlockAnalyzer.analyze",
                return_value={"bullish": {"low": 128.0, "high": 131.0}, "bearish": None},
            ),
            patch(
                "app.analysis.pro.engine.FVGAnalyzer.analyze",
                return_value={"type": "BULLISH", "top": 131.0, "bottom": 128.0},
            ),
            patch(
                "app.analysis.pro.engine.SwingAnalyzer.analyze",
                return_value=([{"price": 125.0, "index": 10}], [{"price": 120.0, "index": 5}]),
            ),
        ):
            result = SignalEnginePro.generate(df, indicators_calculated=True)

        assert result["signal"] == "BUY"
        assert result["confidence"] >= 65
        assert result["entry"] is not None
        assert result["stop"] is not None
        assert result["tp"] is not None
        assert result["risk_reward"] >= 1.0
        assert result["explanation"]
        assert len(result["reasons"]) >= 3
        assert result["setup_type"] == "pro_signal"

    def test_signal_generator_delegates_to_pro(self, sample_with_indicators):
        result = SignalGenerator.generate(sample_with_indicators, indicators_calculated=True)
        assert result["signal"] in ("BUY", "SELL", "WAIT")
        assert "explanation" in result
        assert isinstance(result["feature_scores"], list)

    def test_output_schema_fields(self, sample_ohlcv):
        df = SignalIndicators.calculate(sample_ohlcv)
        result = SignalEnginePro.generate(df, indicators_calculated=True)
        for key in (
            "signal",
            "score",
            "confidence",
            "entry",
            "stop",
            "tp",
            "reasons",
            "explanation",
            "trend",
            "bos",
            "choch",
            "feature_scores",
            "buy_confidence",
            "sell_confidence",
        ):
            assert key in result
