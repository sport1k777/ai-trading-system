"""Signal Engine PRO V2 — sequential SMC narrative engine."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from app.analysis.market_context import MarketContext, MarketContextBuilder
from app.analysis.pro_v2.confirmations import run_confirmations
from app.analysis.pro_v2.dealing_range import compute_dealing_range
from app.analysis.pro_v2.grader import assign_grade, direction_from_narrative, grade_emits_signal
from app.analysis.pro_v2.htf_bias import evaluate_htf_bias
from app.analysis.pro_v2.models import ProV2Signal
from app.analysis.pro_v2.regime_gate import run_regime_gates
from app.analysis.pro_v2.risk_gate import check_risk_levels
from app.analysis.pro_v2.setup_sequence import (
    confluence_core_aligned,
    pick_best_narrative,
)
from app.risk.risk_manager_v2 import RiskManagerV2

logger = logging.getLogger(__name__)

REQUIRED = MarketContextBuilder.REQUIRED


class SignalEngineProV2:
    """Production SMC engine with gates, sequential narrative, and graded output."""

    REQUIRED = REQUIRED

    @staticmethod
    def generate(
        df: pd.DataFrame,
        *,
        indicators_calculated: bool = False,
        context: Optional[MarketContext] = None,
        symbol: str = "BTCUSDT",
        interval: str = "15",
        htf_df: Optional[pd.DataFrame] = None,
    ) -> dict:
        if len(df) < 50:
            return SignalEngineProV2._wait("Insufficient candle history")

        ctx = context or MarketContextBuilder.build(
            df,
            symbol=symbol,
            interval=interval,
            htf_df=htf_df,
            indicators_calculated=indicators_calculated,
        )

        if not MarketContextBuilder.is_ready(ctx):
            return SignalEngineProV2._wait("Indicators not ready", ctx)

        narrative = pick_best_narrative(ctx)
        direction = direction_from_narrative(narrative)

        core_ok, _ = (
            confluence_core_aligned(ctx, direction) if direction else (False, "")
        )
        gates = run_regime_gates(
            ctx,
            direction,
            allow_bos_structure_override=core_ok,
        )
        gates_passed = [g.name for g in gates if g.passed]
        gates_failed = [f"{g.name}: {g.reason}" for g in gates if not g.passed and g.blocking]

        if any(not g.passed and g.blocking for g in gates):
            return SignalEngineProV2._wait(
                f"Regime gate failed: {gates_failed[0] if gates_failed else 'unknown'}",
                ctx,
                gates_passed=gates_passed,
                gates_failed=gates_failed,
            )

        if not narrative.complete or direction is None:
            missing = [s.name for s in narrative.steps if not s.completed]
            return SignalEngineProV2._wait(
                f"Setup incomplete ({narrative.summary}); missing: {', '.join(missing[:3])}",
                ctx,
                gates_passed=gates_passed,
                gates_failed=gates_failed,
                narrative=narrative.summary,
            )

        htf = evaluate_htf_bias(ctx)
        confirmations = run_confirmations(ctx, direction)
        conf_reasons = [f"{c.name}: {c.reason}" for c in confirmations if c.aligned]

        sl = ctx.swing_lows[-1]["price"] if ctx.swing_lows else None
        sh = ctx.swing_highs[-1]["price"] if ctx.swing_highs else None
        risk = RiskManagerV2.calculate(ctx, direction, swing_low=sl, swing_high=sh)
        risk_gate = check_risk_levels(risk)
        if not risk_gate.passed:
            gates_failed.append(risk_gate.reason)
            return SignalEngineProV2._wait(risk_gate.reason, ctx, gates_failed=gates_failed)

        grade, confidence = assign_grade(narrative, confirmations, htf, risk)

        if not grade_emits_signal(grade):
            return SignalEngineProV2._wait(
                f"Grade {grade} below minimum actionable grade",
                ctx,
                grade=grade,
                confidence=confidence,
                gates_passed=gates_passed,
                narrative=narrative.summary,
            )

        dealing = compute_dealing_range(ctx)
        step_reasons = [f"{s.name}: {s.reason}" for s in narrative.steps if s.completed]
        reasons = gates_passed + step_reasons + conf_reasons
        reasons.append(
            f"Entry={risk['entry']} ({risk.get('entry_type', 'market')}) "
            f"SL={risk['stop']} TP1={risk['tp1']} "
            f"R:R TP1=1:{risk.get('rr_tp1', risk['rr']):.2f} "
            f"TP2=1:{risk.get('rr_tp2', 0):.2f} TP3=1:{risk.get('rr_tp3', 0):.2f}"
        )

        explanation = SignalEngineProV2._build_explanation(
            direction, grade, confidence, narrative, htf, dealing.zone, reasons,
        )

        feature_scores = SignalEngineProV2._to_feature_scores(confirmations, narrative)

        result = ProV2Signal(
            signal=direction,
            grade=grade,
            confidence=confidence,
            direction=narrative.direction,
            entry=risk["entry"],
            stop=risk["stop"],
            tp=risk["tp1"],
            tp1=risk["tp1"],
            tp2=risk["tp2"],
            tp3=risk["tp3"],
            risk_reward=risk["rr"],
            reasons=reasons,
            explanation=explanation,
            gates_passed=gates_passed,
            gates_failed=gates_failed,
            narrative=narrative.summary,
            htf_bias=htf.reason,
            dealing_range_zone=dealing.zone,
            feature_scores=feature_scores,
            buy_confidence=confidence if direction == "BUY" else 0,
            sell_confidence=confidence if direction == "SELL" else 0,
            trend=ctx.trend,
            structure=ctx.structure,
            bos=ctx.bos,
            choch=ctx.choch,
            liquidity=ctx.liquidity,
            orderblock=ctx.order_block,
            fvg=ctx.fvg,
            swing_highs=ctx.swing_highs,
            swing_lows=ctx.swing_lows,
        )
        logger.info(
            "%s PRO V2 %s grade=%s confidence=%.1f",
            symbol, direction, grade, confidence,
        )
        return result.to_dict()

    @staticmethod
    def _to_feature_scores(confirmations, narrative) -> list[dict]:
        rows = []
        for c in confirmations:
            buy = sell = 50.0
            if c.aligned:
                if narrative.direction == "LONG":
                    buy = 80.0
                elif narrative.direction == "SHORT":
                    sell = 80.0
            rows.append({"name": c.name, "buy_score": buy, "sell_score": sell, "reason": c.reason})
        for s in narrative.steps:
            buy = sell = 50.0
            if s.completed:
                if narrative.direction == "LONG":
                    buy = 75.0
                elif narrative.direction == "SHORT":
                    sell = 75.0
            rows.append({"name": s.name, "buy_score": buy, "sell_score": sell, "reason": s.reason})
        return rows

    @staticmethod
    def _build_explanation(direction, grade, confidence, narrative, htf, zone, reasons) -> str:
        side = "LONG" if direction == "BUY" else "SHORT"
        lines = [
            f"Signal Engine PRO V2 — {side}",
            f"Grade: {grade} | Confidence: {confidence:.1f}/100",
            f"Narrative: {narrative.summary}",
            f"HTF: {htf.reason}",
            f"Dealing Range: {zone}",
            "Confluence:",
        ]
        lines.extend(f"- {r}" for r in reasons[:12])
        return "\n".join(lines)

    @staticmethod
    def _wait(
        reason: str,
        ctx: Optional[MarketContext] = None,
        **extra,
    ) -> dict:
        meta = {}
        if ctx:
            meta = {
                "trend": ctx.trend,
                "structure": ctx.structure,
                "bos": ctx.bos,
                "choch": ctx.choch,
                "liquidity": ctx.liquidity,
                "orderblock": ctx.order_block,
                "fvg": ctx.fvg,
                "swing_highs": ctx.swing_highs,
                "swing_lows": ctx.swing_lows,
            }
        return {
            "signal": "WAIT",
            "score": 0,
            "confluence": 0,
            "confidence": extra.get("confidence", 0),
            "grade": extra.get("grade", "C"),
            "setup_type": "none",
            "tp_price": None,
            "entry": None,
            "stop": None,
            "tp": None,
            "reasons": [reason],
            "explanation": reason,
            "narrative": extra.get("narrative", ""),
            "htf_bias": "",
            "gates_passed": extra.get("gates_passed", []),
            "gates_failed": extra.get("gates_failed", []),
            "feature_scores": [],
            "buy_confidence": 0,
            "sell_confidence": 0,
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
