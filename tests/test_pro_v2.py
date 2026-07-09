"""Tests for Signal Engine PRO V2."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from app.analysis.market_context import MarketContextBuilder
from app.analysis.pro_v2.dealing_range import compute_dealing_range, zone_allows
from app.analysis.pro_v2.engine import SignalEngineProV2
from app.analysis.pro_v2.grader import assign_grade, grade_emits_signal
from app.analysis.pro_v2.htf_bias import evaluate_htf_bias
from app.analysis.pro_v2.models import ConfirmationResult, SetupNarrative, SetupType, SequenceStep
from app.analysis.pro_v2.regime_gate import check_atr_gate, check_adx_gate
from app.analysis.signal_generator import SignalGenerator
from app.indicators.signals import SignalIndicators


@pytest.fixture
def v2_context(sample_ohlcv):
    df = SignalIndicators.calculate(sample_ohlcv)
    return MarketContextBuilder.build(df, symbol="BTCUSDT", interval="15", indicators_calculated=True)


class TestMarketContext:
    def test_builds_closed_bar_context(self, sample_ohlcv):
        ctx = MarketContextBuilder.build(sample_ohlcv)
        assert len(ctx.analysis_df) == len(sample_ohlcv) - 1
        assert ctx.trend in ("BULLISH", "BEARISH", "SIDEWAYS")

    def test_resample_htf(self, sample_ohlcv):
        df = SignalIndicators.calculate(sample_ohlcv)
        htf = MarketContextBuilder.resample_htf(df, bars_per_htf=4)
        assert len(htf) >= 10


class TestGates:
    def test_atr_gate(self, v2_context):
        gate = check_atr_gate(v2_context)
        assert gate.name == "ATR Volatility"

    def test_adx_gate(self, v2_context):
        gate = check_adx_gate(v2_context)
        assert isinstance(gate.passed, bool)


class TestDealingRange:
    def test_zone_detection(self, v2_context):
        dr = compute_dealing_range(v2_context)
        assert dr.zone in ("discount", "premium", "equilibrium")
        assert dr.high >= dr.low


class TestGrader:
    def test_grade_a_plus(self):
        narrative = SetupNarrative(
            setup_type=SetupType.CONTINUATION,
            direction="LONG",
            steps=[SequenceStep("HTF Bias", True, "ok")],
            complete=True,
        )
        confs = [
            ConfirmationResult("EMA", True, "ok"),
            ConfirmationResult("RSI", True, "ok"),
            ConfirmationResult("VWAP", True, "ok"),
        ]
        from app.analysis.pro_v2.models import HTFBias
        htf = HTFBias("LONG", "BULLISH", "UPTREND", "BULLISH_BOS", "strong", 90)
        grade, confidence = assign_grade(narrative, confs, htf, 2.6)
        assert grade in ("A+", "A")
        assert confidence >= 85

    def test_grade_c_does_not_emit(self):
        assert grade_emits_signal("C") is False
        assert grade_emits_signal("A") is True


class TestSignalEngineProV2:
    def test_wait_on_short_data(self):
        df = pd.DataFrame({"open": [1.0] * 10, "high": [1.1] * 10, "low": [0.9] * 10, "close": [1.0] * 10})
        result = SignalEngineProV2.generate(df)
        assert result["signal"] == "WAIT"

    def test_output_schema(self, v2_context):
        result = SignalEngineProV2.generate(v2_context.df, context=v2_context, indicators_calculated=True)
        for key in ("signal", "confidence", "grade", "reasons", "explanation", "gates_passed"):
            assert key in result

    def test_generates_signal_with_full_setup(self, sample_ohlcv):
        df = SignalIndicators.calculate(sample_ohlcv)
        last = len(df) - 1
        df.loc[last, "close"] = 130.0
        df.loc[last, "open"] = 129.0
        df.loc[last, "rsi"] = 55.0
        df.loc[last, "volume_ratio"] = 1.4
        df.loc[last, "atr_pct"] = 0.8
        df.loc[last, "adx"] = 30.0

        with (
            patch("app.analysis.pro_v2.engine.pick_best_narrative") as mock_narr,
            patch("app.analysis.pro_v2.engine.run_regime_gates") as mock_gates,
            patch("app.analysis.pro_v2.engine.check_risk_levels") as mock_risk,
            patch("app.analysis.pro_v2.engine.assign_grade", return_value=("A", 88.0)),
            patch("app.analysis.pro_v2.engine.grade_emits_signal", return_value=True),
            patch("app.analysis.pro_v2.engine.RiskManagerV2.calculate") as mock_rm,
        ):
            from app.analysis.pro_v2.models import GateResult
            mock_gates.return_value = [GateResult("ATR", True, "ok")]
            mock_risk.return_value = GateResult("Risk", True, "ok")
            mock_narr.return_value = SetupNarrative(
                setup_type=SetupType.CONTINUATION,
                direction="LONG",
                steps=[SequenceStep("HTF Bias", True, "ok"), SequenceStep("Confirmation", True, "ok")],
                complete=True,
                summary="Continuation LONG complete",
            )
            mock_rm.return_value = {
                "entry": 130.0, "stop": 128.0, "tp1": 134.0, "tp2": 135.0, "tp3": 136.0, "rr": 2.2, "risk": 2.0, "tp": 134.0,
            }
            ctx = MarketContextBuilder.build(df, indicators_calculated=True)
            result = SignalEngineProV2.generate(df, context=ctx, indicators_calculated=True)

        assert result["signal"] == "BUY"
        assert result["grade"] == "A"
        assert result["confidence"] >= 85


class TestSignalGeneratorRouting:
    def test_v1_default(self, sample_with_indicators):
        with patch("app.analysis.signal_generator.SIGNAL_ENGINE_VERSION", "v1"):
            from importlib import reload
            import app.analysis.signal_generator as sg
            reload(sg)
            result = sg.SignalGenerator.generate(sample_with_indicators, indicators_calculated=True)
            assert result["signal"] in ("BUY", "SELL", "WAIT")
