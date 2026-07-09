"""Signal Engine PRO — confluence-based production signal generation."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from app.analysis.bos import BOSAnalyzer
from app.analysis.choch import CHOCHAnalyzer
from app.analysis.fvg import FVGAnalyzer
from app.analysis.liquidity import LiquidityAnalyzer
from app.analysis.order_block import OrderBlockAnalyzer
from app.analysis.market_context import MarketContext
from app.analysis.pro.conditions import is_volatility_tradeable
from app.analysis.pro.confluence import (
    build_explanation,
    conditions_to_feature_scores,
    pick_direction,
    score_confluence,
)
from app.analysis.structure import StructureAnalyzer
from app.analysis.swing import SwingAnalyzer
from app.config import (
    PRO_MIN_CONDITIONS,
    PRO_MIN_CONFIDENCE,
    PRO_MIN_DIRECTION_GAP,
)
from app.indicators.signals import SignalIndicators
from app.indicators.trend import TrendAnalyzer
from app.risk.risk_manager import RiskManager

LOOKBACK = 100

REQUIRED = (
    "ema20",
    "ema50",
    "ema200",
    "rsi",
    "macd_diff",
    "atr",
    "adx",
    "bb_upper",
    "bb_mid",
    "bb_lower",
)


class SignalEnginePro:
    """
    Confluence engine that emits LONG/SHORT only when multiple independent
    market-structure and momentum conditions align.
    """

    REQUIRED = REQUIRED

    @staticmethod
    def _ready(last: pd.Series) -> bool:
        return all(pd.notna(last.get(c)) for c in REQUIRED)

    @staticmethod
    def generate(
        df: pd.DataFrame,
        *,
        indicators_calculated: bool = False,
        context: Optional[MarketContext] = None,
    ) -> dict:
        if len(df) < 50 and context is None:
            return SignalEnginePro._wait("Insufficient candle history")

        if context is not None:
            df = context.df
            last = context.last
            trend = context.trend
            structure = context.structure
            bos = context.bos
            choch = context.choch
            liquidity = context.liquidity
            order_block = context.order_block
            fvg = context.fvg
            swing_highs = context.swing_highs
            swing_lows = context.swing_lows
        else:
            if not indicators_calculated:
                df = SignalIndicators.calculate(df)
            last = df.iloc[-1]
            if not SignalEnginePro._ready(last):
                return SignalEnginePro._wait("Indicators not ready")
            view = df.iloc[-LOOKBACK:] if len(df) > LOOKBACK else df
            trend = TrendAnalyzer.detect_trend(view)
            structure = StructureAnalyzer.analyze(view)
            bos = BOSAnalyzer.analyze(view)
            choch = CHOCHAnalyzer.analyze(view)
            liquidity = LiquidityAnalyzer.analyze(view)
            order_block = OrderBlockAnalyzer.analyze(view)
            fvg = FVGAnalyzer.analyze(view)
            swing_highs, swing_lows = SwingAnalyzer.analyze(view, lookback=50)

        if not SignalEnginePro._ready(last):
            return SignalEnginePro._wait("Indicators not ready")

        vol_ok, vol_reason = is_volatility_tradeable(last)
        if not vol_ok:
            return SignalEnginePro._wait(vol_reason)

        price = float(last["close"])
        atr = float(last["atr"])

        confluence = score_confluence(
            last=last,
            trend=trend,
            bos=bos,
            choch=choch,
            liquidity=liquidity,
            order_block=order_block,
            fvg=fvg,
        )

        direction, confidence, reasons = pick_direction(
            confluence,
            min_conditions=PRO_MIN_CONDITIONS,
            min_confidence=PRO_MIN_CONFIDENCE,
            min_gap=PRO_MIN_DIRECTION_GAP,
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
            setup_type="pro_signal",
            tp_price=None,
            feature_scores=conditions_to_feature_scores(confluence.conditions),
            buy_confidence=confluence.long_score,
            sell_confidence=confluence.short_score,
            confluence_hits={
                "long": confluence.long_hits,
                "short": confluence.short_hits,
            },
        )

        if direction is None:
            best = max(confluence.long_score, confluence.short_score)
            return SignalEnginePro._wait(
                f"Confluence insufficient (best score {best:.1f}, "
                f"need {PRO_MIN_CONDITIONS} factors and {PRO_MIN_CONFIDENCE:.0f} confidence)",
                **meta,
            )

        sl_price = swing_lows[-1]["price"] if swing_lows else None
        sh_price = swing_highs[-1]["price"] if swing_highs else None
        risk = RiskManager.calculate(
            price,
            atr,
            direction,
            swing_low=sl_price,
            swing_high=sh_price,
            setup_type="pro_signal",
        )
        if not risk:
            return SignalEnginePro._wait("Could not calculate risk levels", **meta)

        reasons = [vol_reason, *reasons]
        explanation = build_explanation(
            direction,
            confidence,
            reasons,
            confluence,
            min_conditions=PRO_MIN_CONDITIONS,
            min_confidence=PRO_MIN_CONFIDENCE,
        )
        reasons.append(
            f"Entry={risk['entry']} SL={risk['stop']} TP={risk['tp1']} RR=1:{risk['rr']}"
        )

        return SignalEnginePro._sig(
            direction,
            confidence,
            reasons,
            explanation=explanation,
            entry=risk["entry"],
            stop=risk["stop"],
            tp=risk["tp1"],
            risk=risk,
            **meta,
        )

    @staticmethod
    def _sig(direction: str, confidence: float, reasons: list[str], **meta) -> dict:
        conf_int = int(round(confidence))
        risk = meta.pop("risk", None)
        payload = {
            "signal": direction,
            "score": conf_int if direction == "BUY" else -conf_int,
            "confluence": conf_int,
            "confidence": round(confidence, 1),
            "setup_type": meta.get("setup_type", "pro_signal"),
            "tp_price": meta.get("tp_price"),
            "entry": meta.get("entry"),
            "stop": meta.get("stop"),
            "tp": meta.get("tp"),
            "reasons": reasons,
            "explanation": meta.get("explanation", ""),
            "feature_scores": meta.get("feature_scores", []),
            "buy_confidence": meta.get("buy_confidence", 0),
            "sell_confidence": meta.get("sell_confidence", 0),
            "confluence_hits": meta.get("confluence_hits", {}),
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
        if risk:
            payload["risk_reward"] = risk["rr"]
            payload["tp1"] = risk["tp1"]
            payload["tp2"] = risk["tp2"]
            payload["tp3"] = risk["tp3"]
        return payload

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
            "explanation": reason,
            "feature_scores": meta.get("feature_scores", []),
            "buy_confidence": meta.get("buy_confidence", 0),
            "sell_confidence": meta.get("sell_confidence", 0),
            "confluence_hits": meta.get("confluence_hits", {}),
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
