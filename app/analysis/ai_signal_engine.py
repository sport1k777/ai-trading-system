"""
AI Signal Engine — multi-feature scoring with confidence-based signal generation.
Replaces rule-based logic while preserving backtester-compatible output schema.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.analysis.bos import BOSAnalyzer
from app.analysis.choch import CHOCHAnalyzer
from app.analysis.feature_scorer import FeatureScorer
from app.analysis.fvg import FVGAnalyzer
from app.analysis.liquidity import LiquidityAnalyzer
from app.analysis.order_block import OrderBlockAnalyzer
from app.analysis.structure import StructureAnalyzer
from app.analysis.swing import SwingAnalyzer
from app.analysis.feature_engine import load_config, load_weights
from app.config import AI_CONFIDENCE_THRESHOLD
from app.indicators.extended import ExtendedIndicators
from app.indicators.signals import SignalIndicators
from app.indicators.trend import TrendAnalyzer
from app.risk.risk_manager import RiskManager

LOOKBACK = 100
WEIGHTS_PATH = Path(".cache/ai_weights.json")
CONFIG_PATH = Path(".cache/ai_config.json")

REQUIRED = (
    "ema20", "ema50", "ema200", "rsi", "macd_diff", "macd_diff_prev",
    "atr", "adx", "bb_upper", "bb_mid", "bb_lower",
)


class AISignalEngine:
    """
    Scores 20+ market features individually, aggregates into a 0-100 confidence
    score, and emits signals only when confidence exceeds the threshold (default 90).
    """

    REQUIRED = REQUIRED

    @staticmethod
    def _load_weights() -> dict[str, float]:
        return load_weights()

    @staticmethod
    def _load_threshold() -> float:
        return float(load_config().get("threshold", AI_CONFIDENCE_THRESHOLD))

    @staticmethod
    def _ready(last: pd.Series) -> bool:
        return all(pd.notna(last.get(c)) for c in REQUIRED)

    @staticmethod
    def generate(df: pd.DataFrame, *, indicators_calculated: bool = False) -> dict:
        if len(df) < 50:
            return AISignalEngine._wait("Insufficient candle history")

        if not indicators_calculated:
            df = SignalIndicators.calculate(df)
            df = ExtendedIndicators.calculate(df)
        elif "vwap" not in df.columns:
            df = ExtendedIndicators.calculate(df)

        last = df.iloc[-1]
        if not AISignalEngine._ready(last):
            return AISignalEngine._wait("Indicators not ready")

        price = float(last["close"])
        atr = float(last["atr"])

        view = df.iloc[-LOOKBACK:] if len(df) > LOOKBACK else df
        trend = TrendAnalyzer.detect_trend(view)
        structure = StructureAnalyzer.analyze(view)
        bos = BOSAnalyzer.analyze(view)
        choch = CHOCHAnalyzer.analyze(view)
        liquidity = LiquidityAnalyzer.analyze(view)
        order_block = OrderBlockAnalyzer.analyze(view)
        fvg = FVGAnalyzer.analyze(view)
        swing_highs, swing_lows = SwingAnalyzer.analyze(view, lookback=50)

        weights = AISignalEngine._load_weights()
        feature_scores = FeatureScorer.score_all(
            view,
            liquidity=liquidity,
            order_block=order_block,
            fvg=fvg,
            structure=structure,
            bos=bos,
            choch=choch,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
        )

        buy_conf, sell_conf, buy_reasons, sell_reasons = FeatureScorer.aggregate(
            feature_scores, weights,
        )

        meta = dict(
            trend=trend,
            structure=structure,
            bos=bos,
            choch=choch,
            liquidity=liquidity,
            orderblock=order_block,
            fvg=fvg,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
            setup_type="ai_signal",
            tp_price=None,
            confidence=0,
            feature_scores=[fs.to_dict() for fs in feature_scores],
            buy_confidence=round(buy_conf, 1),
            sell_confidence=round(sell_conf, 1),
        )

        threshold = AISignalEngine._load_threshold()
        direction = None
        confidence = 0.0
        reasons: list[str] = []

        if buy_conf >= threshold and buy_conf > sell_conf + 8:
            direction = "BUY"
            confidence = buy_conf
            reasons = buy_reasons[:8]
            reasons.insert(0, f"AI confidence {buy_conf:.1f}/100 (threshold {threshold})")
        elif sell_conf >= threshold and sell_conf > buy_conf + 8:
            direction = "SELL"
            confidence = sell_conf
            reasons = sell_reasons[:8]
            reasons.insert(0, f"AI confidence {sell_conf:.1f}/100 (threshold {threshold})")

        if direction is None:
            best = max(buy_conf, sell_conf)
            return AISignalEngine._wait(
                f"Confidence {best:.1f} below threshold {threshold}",
                **meta,
            )

        meta["confidence"] = round(confidence, 1)
        sl_price = swing_lows[-1]["price"] if swing_lows else None
        sh_price = swing_highs[-1]["price"] if swing_highs else None

        risk = RiskManager.calculate(
            price, atr, direction,
            swing_low=sl_price, swing_high=sh_price,
            setup_type="ai_signal",
        )

        if risk:
            meta["entry"] = risk["entry"]
            meta["stop"] = risk["stop"]
            meta["tp"] = risk["tp1"]
            reasons.append(f"Entry={risk['entry']} SL={risk['stop']} TP={risk['tp1']} RR={risk['rr']}")

        return AISignalEngine._sig(direction, confidence, reasons, **meta)

    @staticmethod
    def _sig(direction: str, confidence: float, reasons: list[str], **meta) -> dict:
        conf_int = int(round(confidence))
        return {
            "signal": direction,
            "score": conf_int if direction == "BUY" else -conf_int,
            "confluence": conf_int,
            "confidence": meta.get("confidence", conf_int),
            "setup_type": meta.get("setup_type", "ai_signal"),
            "tp_price": meta.get("tp_price"),
            "entry": meta.get("entry"),
            "stop": meta.get("stop"),
            "tp": meta.get("tp"),
            "reasons": reasons,
            "feature_scores": meta.get("feature_scores", []),
            "buy_confidence": meta.get("buy_confidence", 0),
            "sell_confidence": meta.get("sell_confidence", 0),
            "trend": meta["trend"],
            "structure": meta["structure"],
            "bos": meta["bos"],
            "choch": meta["choch"],
            "liquidity": meta["liquidity"],
            "orderblock": meta["orderblock"],
            "fvg": meta["fvg"],
            "swing_highs": meta["swing_highs"],
            "swing_lows": meta["swing_lows"],
        }

    @staticmethod
    def _wait(reason: str, **meta) -> dict:
        return {
            "signal": "WAIT",
            "score": 0,
            "confluence": 0,
            "confidence": 0,
            "setup_type": "none",
            "tp_price": None,
            "entry": None,
            "stop": None,
            "tp": None,
            "reasons": [reason],
            "feature_scores": meta.get("feature_scores", []),
            "buy_confidence": meta.get("buy_confidence", 0),
            "sell_confidence": meta.get("sell_confidence", 0),
            "trend": meta.get("trend", "SIDEWAYS"),
            "structure": meta.get("structure", "RANGE"),
            "bos": meta.get("bos", "NO_BOS"),
            "choch": meta.get("choch", "NO_CHOCH"),
            "liquidity": meta.get("liquidity"),
            "orderblock": meta.get("orderblock"),
            "fvg": meta.get("fvg"),
            "swing_highs": meta.get("swing_highs", []),
            "swing_lows": meta.get("swing_lows", []),
        }
