"""Per-scan signal pipeline diagnostics — identifies exact rejection points."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import pandas as pd

from app.analysis.market_context import MarketContext, MarketContextBuilder
from app.analysis.market_regime import (
    build_regime_profile,
    detect_regime_from_context,
    is_volatility_tradeable_regime,
    validate_regime_confirmations,
)
from app.analysis.poi_proximity import near_bearish_poi, near_bullish_poi
from app.analysis.pro.conditions import evaluate_all, evaluate_volume, is_volatility_tradeable
from app.analysis.pro.engine import SignalEnginePro
from app.analysis.pro.confluence import pick_direction, score_confluence
from app.analysis.pro_v2.confirmations import (
    check_ema_stack,
    check_rsi,
    run_confirmations,
)
from app.analysis.pro_v2.grader import assign_grade, grade_emits_signal
from app.analysis.pro_v2.htf_bias import evaluate_htf_bias, htf_allows
from app.analysis.pro_v2.regime_gate import check_adx_gate, check_atr_gate, run_regime_gates
from app.analysis.pro_v2.risk_gate import check_risk_levels
from app.analysis.pro_v2.setup_sequence import (
    _poi_return,
    _structure_break,
    pick_best_narrative,
    validate_continuation,
    validate_reversal,
)
from app.analysis.pro_v2.liquidity_pools import liquidity_swept_recently
from app.analysis.signal_generator import SignalGenerator
from app.config import (
    MIN_ADX,
    PRO_CONDITION_WEIGHTS,
    PRO_MIN_CONDITIONS,
    PRO_MIN_CONFIDENCE,
    PRO_MIN_DIRECTION_GAP,
    PRO_V2_HTF_INTERVAL,
    PRO_V2_MIN_ADX,
    SIGNAL_ENGINE_VERSION,
    TELEGRAM_NOTIFY_MIN_CONFIDENCE,
)
from app.risk.risk_manager import RiskManager
from app.risk.risk_manager_v2 import RiskManagerV2

if TYPE_CHECKING:
    from app.pipeline import AnalysisResult, TradingPipeline


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ScanDiagnostic:
    symbol: str
    engine_version: str
    timeframe: str
    candidate_direction: str
    checks: list[CheckResult] = field(default_factory=list)
    structure: str = "UNKNOWN"
    confidence: float = 0.0
    grade: str = "—"
    engine_signal: str = "WAIT"
    risk_ok: bool = False
    risk_detail: str = ""
    rejection_reason: str = ""
    telegram_blocked: bool = False
    would_alert: bool = False
    regime: str = ""
    regime_trend: str = ""
    regime_volatility: str = ""
    final_decision: str = "WAIT"

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


def _pass_fail(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _bos_pass(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    if direction == "BUY":
        ok = ctx.bos == "BULLISH_BOS"
        return ok, ctx.bos if ok else f"No bullish BOS ({ctx.bos})"
    ok = ctx.bos == "BEARISH_BOS"
    return ok, ctx.bos if ok else f"No bearish BOS ({ctx.bos})"


def _choch_pass(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    if direction == "BUY":
        ok = ctx.choch == "BULLISH_CHOCH"
        return ok, ctx.choch if ok else f"No bullish CHOCH ({ctx.choch})"
    ok = ctx.choch == "BEARISH_CHOCH"
    return ok, ctx.choch if ok else f"No bearish CHOCH ({ctx.choch})"


def _liquidity_pass(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    ok, reason = liquidity_swept_recently(ctx, direction)
    if ok:
        return True, reason
    liq = ctx.liquidity
    if not liq:
        return False, "No liquidity sweep detected"
    return False, f"Sweep type {liq.get('type')} not aligned for {direction}"


def _order_block_pass(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    ok, reason = _poi_return(ctx, direction)
    ob = ctx.order_block
    if ob:
        if direction == "BUY" and ob.get("bullish"):
            b = ob["bullish"]
            if near_bullish_poi(ctx.price, b["low"], b["high"]):
                return True, f"Bullish OB {b['low']:.2f}–{b['high']:.2f}"
        if direction == "SELL" and ob.get("bearish"):
            b = ob["bearish"]
            if near_bearish_poi(ctx.price, b["low"], b["high"]):
                return True, f"Bearish OB {b['low']:.2f}–{b['high']:.2f}"
    if ok and "OB" in reason:
        return True, reason
    if ob:
        return False, "Order block present but price outside 0.3% proximity"
    return False, reason if not ok else "No aligned order block"


def _fvg_pass(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    ok, reason = _poi_return(ctx, direction)
    fvg = ctx.fvg
    if fvg:
        if direction == "BUY" and fvg.get("type") == "BULLISH":
            if near_bullish_poi(ctx.price, fvg["bottom"], fvg["top"]):
                return True, f"Bullish FVG {fvg['bottom']:.2f}–{fvg['top']:.2f}"
        if direction == "SELL" and fvg.get("type") == "BEARISH":
            if near_bearish_poi(ctx.price, fvg["bottom"], fvg["top"]):
                return True, f"Bearish FVG {fvg['bottom']:.2f}–{fvg['top']:.2f}"
    if ok and "FVG" in reason:
        return True, reason
    if fvg:
        return False, f"Active {fvg.get('type', 'unknown')} FVG outside 0.3% proximity"
    return False, "No active FVG"


def _ema_pass_v1(ctx: MarketContext, direction: str, trend: str) -> tuple[bool, str]:
    close = float(ctx.last["close"])
    ema50 = float(ctx.last["ema50"])
    if direction == "BUY":
        ok = trend == "BULLISH" and close > ema50
        return ok, "Bullish EMA trend" if ok else f"Trend={trend}, close vs EMA50 misaligned"
    ok = trend == "BEARISH" and close < ema50
    return ok, "Bearish EMA trend" if ok else f"Trend={trend}, close vs EMA50 misaligned"


def _rsi_pass_v1(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    rsi = float(ctx.last["rsi"])
    if direction == "BUY":
        ok = 45 <= rsi <= 68
        return ok, f"RSI {rsi:.1f}" + ("" if ok else " outside bullish zone 45–68")
    ok = 32 <= rsi <= 55
    return ok, f"RSI {rsi:.1f}" + ("" if ok else " outside bearish zone 32–55")


def _adx_pass(ctx: MarketContext, *, min_adx: float) -> tuple[bool, str]:
    adx = float(ctx.last.get("adx", 0))
    if pd.isna(adx):
        return False, "ADX unavailable"
    ok = adx >= min_adx
    return ok, f"ADX {adx:.1f} (min {min_adx:.0f})"


def _atr_pass(ctx: MarketContext) -> tuple[bool, str]:
    regime = ctx.regime or detect_regime_from_context(ctx)
    profile = build_regime_profile(regime)
    return is_volatility_tradeable_regime(ctx.last, profile)


def _trend_pass(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    trend = ctx.trend
    if direction == "BUY":
        ok = trend == "BULLISH"
        return ok, f"LTF trend={trend}" + ("" if ok else " — need BULLISH for BUY")
    ok = trend == "BEARISH"
    return ok, f"LTF trend={trend}" + ("" if ok else " — need BEARISH for SELL")


def _volume_pass(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    weight = PRO_CONDITION_WEIGHTS.get("volume", PRO_CONDITION_WEIGHTS["rsi"])
    cond = evaluate_volume(ctx.last, weight=weight)
    if direction == "BUY":
        ok = cond.aligned and cond.direction == "LONG"
    else:
        ok = cond.aligned and cond.direction == "SHORT"
    return ok, cond.reason


def _htf_pass_v2(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    bias = evaluate_htf_bias(ctx)
    ok = htf_allows(direction, bias)
    return ok, bias.reason


def _htf_pass_v1(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    htf = ctx.htf_trend
    if direction == "BUY":
        ok = htf == "BULLISH" or (htf == "SIDEWAYS" and ctx.trend == "BULLISH")
        detail = f"HTF {htf}, LTF {ctx.trend}"
        return ok, detail + ("" if ok else " — no bullish HTF alignment")
    ok = htf == "BEARISH" or (htf == "SIDEWAYS" and ctx.trend == "BEARISH")
    detail = f"HTF {htf}, LTF {ctx.trend}"
    return ok, detail + ("" if ok else " — no bearish HTF alignment")


def _candidate_direction_v1(signal: dict) -> str:
    long_score = float(signal.get("buy_confidence", 0))
    short_score = float(signal.get("sell_confidence", 0))
    return "BUY" if long_score >= short_score else "SELL"


def _candidate_direction_v2(ctx: MarketContext) -> str:
    narrative = pick_best_narrative(ctx)
    if narrative.direction == "LONG":
        return "BUY"
    if narrative.direction == "SHORT":
        return "SELL"
    long_steps = sum(s.completed for s in validate_continuation(ctx, "BUY").steps)
    short_steps = sum(s.completed for s in validate_continuation(ctx, "SELL").steps)
    return "BUY" if long_steps >= short_steps else "SELL"


def _build_checks_v1(ctx: MarketContext, direction: str) -> list[CheckResult]:
    trend_ok, trend_detail = _trend_pass(ctx, direction)
    htf_ok, htf_detail = _htf_pass_v1(ctx, direction)
    bos_ok, bos_detail = _bos_pass(ctx, direction)
    choch_ok, choch_detail = _choch_pass(ctx, direction)
    liq_ok, liq_detail = _liquidity_pass(ctx, direction)
    ob_ok, ob_detail = _order_block_pass(ctx, direction)
    fvg_ok, fvg_detail = _fvg_pass(ctx, direction)
    ema_ok, ema_detail = _ema_pass_v1(ctx, direction, ctx.trend)
    adx_ok, adx_detail = _adx_pass(ctx, min_adx=MIN_ADX)
    rsi_ok, rsi_detail = _rsi_pass_v1(ctx, direction)
    vol_ok, vol_detail = _volume_pass(ctx, direction)
    atr_ok, atr_detail = _atr_pass(ctx)

    regime = ctx.regime or detect_regime_from_context(ctx)
    confluence = score_confluence(
        last=ctx.last,
        trend=ctx.trend,
        bos=ctx.bos,
        choch=ctx.choch,
        liquidity=ctx.liquidity,
        order_block=ctx.order_block,
        fvg=ctx.fvg,
        htf_trend=ctx.htf_trend,
        structure=ctx.structure,
        regime=regime,
    )
    regime_ok, regime_detail = validate_regime_confirmations(
        regime,
        direction,
        confluence.conditions,
        trend=ctx.trend,
        htf_trend=ctx.htf_trend,
        bos=ctx.bos,
        choch=ctx.choch,
    )

    return [
        CheckResult("Trend", trend_ok, trend_detail),
        CheckResult("HTF", htf_ok, htf_detail),
        CheckResult("BOS", bos_ok, bos_detail),
        CheckResult("CHOCH", choch_ok, choch_detail),
        CheckResult("Liquidity", liq_ok, liq_detail),
        CheckResult("Order Block", ob_ok, ob_detail),
        CheckResult("FVG", fvg_ok, fvg_detail),
        CheckResult("EMA", ema_ok, ema_detail),
        CheckResult("ADX", adx_ok, adx_detail),
        CheckResult("RSI", rsi_ok, rsi_detail),
        CheckResult("Volume", vol_ok, vol_detail),
        CheckResult("ATR", atr_ok, atr_detail),
        CheckResult("Regime", regime_ok, regime_detail),
    ]


def _build_checks_v2(ctx: MarketContext, direction: str) -> list[CheckResult]:
    htf_ok, htf_detail = _htf_pass_v2(ctx, direction)
    struct_ok, struct_detail = _structure_break(ctx, direction)
    bos_ok, bos_detail = _bos_pass(ctx, direction)
    choch_ok, choch_detail = _choch_pass(ctx, direction)
    liq_ok, liq_detail = _liquidity_pass(ctx, direction)
    ob_ok, ob_detail = _order_block_pass(ctx, direction)
    fvg_ok, fvg_detail = _fvg_pass(ctx, direction)
    ema = check_ema_stack(ctx, direction)
    rsi = check_rsi(ctx, direction)
    adx_gate = check_adx_gate(ctx)
    atr_gate = check_atr_gate(ctx)

    bos_pass = bos_ok or (struct_ok and "BOS" in struct_detail)
    choch_pass = choch_ok or (struct_ok and "CHOCH" in struct_detail)

    return [
        CheckResult("HTF", htf_ok, htf_detail),
        CheckResult("BOS", bos_pass, struct_detail if struct_ok else bos_detail),
        CheckResult("CHOCH", choch_pass, struct_detail if struct_ok and "CHOCH" in struct_detail else choch_detail),
        CheckResult("Liquidity", liq_ok, liq_detail),
        CheckResult("Order Block", ob_ok, ob_detail),
        CheckResult("FVG", fvg_ok, fvg_detail),
        CheckResult("EMA", ema.aligned, ema.reason),
        CheckResult("ADX", adx_gate.passed, adx_gate.reason),
        CheckResult("RSI", rsi.aligned, rsi.reason),
        CheckResult("ATR", atr_gate.passed, atr_gate.reason),
    ]


def _v1_confidence(ctx: MarketContext, direction: str) -> tuple[float, str]:
    regime = ctx.regime or detect_regime_from_context(ctx)
    confluence = score_confluence(
        last=ctx.last,
        trend=ctx.trend,
        bos=ctx.bos,
        choch=ctx.choch,
        liquidity=ctx.liquidity,
        order_block=ctx.order_block,
        fvg=ctx.fvg,
        htf_trend=ctx.htf_trend,
        structure=ctx.structure,
        regime=regime,
    )
    picked, confidence, _ = pick_direction(
        confluence,
        min_conditions=PRO_MIN_CONDITIONS,
        min_confidence=PRO_MIN_CONFIDENCE,
        min_gap=PRO_MIN_DIRECTION_GAP,
    )
    side_score = confluence.long_score if direction == "BUY" else confluence.short_score
    side_hits = confluence.long_hits if direction == "BUY" else confluence.short_hits
    grade = "A" if side_score >= 80 and side_hits >= PRO_MIN_CONDITIONS else (
        "B" if side_score >= PRO_MIN_CONFIDENCE else "C"
    )
    if picked == direction:
        return confidence, grade
    return side_score, grade


def _v2_confidence(ctx: MarketContext, direction: str) -> tuple[float, str, str]:
    narrative = pick_best_narrative(ctx)
    if direction == "BUY":
        cont = validate_continuation(ctx, "BUY")
        rev = validate_reversal(ctx, "BUY")
        narrative = cont if sum(s.completed for s in cont.steps) >= sum(s.completed for s in rev.steps) else rev
    else:
        cont = validate_continuation(ctx, "SELL")
        rev = validate_reversal(ctx, "SELL")
        narrative = cont if sum(s.completed for s in cont.steps) >= sum(s.completed for s in rev.steps) else rev

    htf = evaluate_htf_bias(ctx)
    confirmations = run_confirmations(ctx, direction)
    sl = ctx.swing_lows[-1]["price"] if ctx.swing_lows else None
    sh = ctx.swing_highs[-1]["price"] if ctx.swing_highs else None
    risk = RiskManagerV2.calculate(ctx, direction, swing_low=sl, swing_high=sh)
    rr = risk["rr"] if risk else 0
    grade, confidence = assign_grade(narrative, confirmations, htf, rr)
    return confidence, grade, narrative.summary


def _resolve_rejection(
    *,
    checks: list[CheckResult],
    engine_signal: str,
    engine_reason: str,
    confidence: float,
    grade: str,
    risk_ok: bool,
    min_confidence: float,
    engine_version: str,
) -> tuple[str, bool, bool]:
    """Return rejection_reason, telegram_blocked, would_alert."""
    if engine_signal in ("BUY", "SELL"):
        if confidence < min_confidence:
            return (
                f"Rejected because Telegram confidence gate failed "
                f"({confidence:.1f} < {min_confidence:.0f})",
                True,
                False,
            )
        if not risk_ok:
            return "Rejected because Risk Manager failed", False, False
        return "Signal accepted — alert eligible", False, True

    failed = [c for c in checks if not c.passed]
    if failed:
        primary = failed[0]
        failed_names = ", ".join(c.name for c in failed[:4])
        base = f"Rejected because {primary.name} failed"
        if engine_reason and engine_reason not in base:
            return f"{base} | Engine: {engine_reason} | Failed: {failed_names}", False, False
        return base, False, False

    if engine_version == "v2" and grade in ("B", "C"):
        return f"Rejected because grade {grade} below minimum actionable grade", False, False

    if engine_reason:
        return f"Rejected because {engine_reason}", False, False

    return "Rejected because setup conditions not met", False, False


def diagnose_scan(
    result: AnalysisResult,
    *,
    timeframe: str,
    min_confidence: float | None = None,
    htf_df: pd.DataFrame | None = None,
) -> ScanDiagnostic:
    """Run full pipeline diagnostic for one symbol scan."""
    min_confidence = min_confidence if min_confidence is not None else TELEGRAM_NOTIFY_MIN_CONFIDENCE
    signal = result.signal
    engine_version = SIGNAL_ENGINE_VERSION

    ctx = MarketContextBuilder.build(
        result.df,
        symbol=result.symbol,
        interval=timeframe,
        htf_df=htf_df,
        indicators_calculated=True,
    )

    if engine_version == "v2":
        direction = _candidate_direction_v2(ctx)
        checks = _build_checks_v2(ctx, direction)
        confidence, grade, _ = _v2_confidence(ctx, direction)
    else:
        direction = _candidate_direction_v1(signal)
        checks = _build_checks_v1(ctx, direction)
        confidence, grade = _v1_confidence(ctx, direction)

    engine_signal = signal.get("signal", "WAIT")
    if engine_signal in ("BUY", "SELL"):
        confidence = float(signal.get("confidence", signal.get("confluence", confidence)))
        grade = str(signal.get("grade", grade))

    risk = result.risk
    if risk:
        if engine_version == "v2":
            risk_gate = check_risk_levels(risk)
            risk_ok = risk_gate.passed
            risk_detail = risk_gate.reason
        else:
            risk_ok = True
            risk_detail = f"R:R 1:{float(risk.get('rr', 0)):.2f}"
    else:
        risk_ok = False
        risk_detail = "Could not compute risk levels"

    engine_reason = signal.get("reasons", ["Unknown"])[0] if signal.get("reasons") else "Unknown"
    rejection, telegram_blocked, would_alert = _resolve_rejection(
        checks=checks,
        engine_signal=engine_signal,
        engine_reason=engine_reason,
        confidence=confidence,
        grade=grade,
        risk_ok=risk_ok,
        min_confidence=min_confidence,
        engine_version=engine_version,
    )

    if would_alert:
        final_decision = f"ALERT {engine_signal}"
    elif engine_signal in ("BUY", "SELL"):
        final_decision = f"BLOCKED ({engine_signal})"
    else:
        final_decision = "WAIT"

    structure = result.structure or signal.get("structure", "UNKNOWN")
    regime_label = signal.get("market_regime", "")
    regime_trend = signal.get("regime_trend", "")
    regime_volatility = signal.get("regime_volatility", "")
    if not regime_label and ctx.regime:
        regime_label = ctx.regime.label
        regime_trend = ctx.regime.trend_regime
        regime_volatility = ctx.regime.volatility_regime

    return ScanDiagnostic(
        symbol=result.symbol,
        engine_version=engine_version,
        timeframe=timeframe,
        candidate_direction=direction,
        checks=checks,
        structure=structure,
        confidence=confidence,
        grade=grade,
        engine_signal=engine_signal,
        risk_ok=risk_ok,
        risk_detail=risk_detail,
        rejection_reason=rejection,
        telegram_blocked=telegram_blocked,
        would_alert=would_alert,
        final_decision=final_decision,
        regime=regime_label,
        regime_trend=regime_trend,
        regime_volatility=regime_volatility,
    )


def diagnose_symbol(
    pipeline: TradingPipeline,
    symbol: str,
    *,
    interval: str,
    min_confidence: float | None = None,
) -> ScanDiagnostic:
    """Fetch candles, run pipeline, and return diagnostic."""
    htf_df = None
    if SIGNAL_ENGINE_VERSION == "v2":
        try:
            htf_df = pipeline.collector.get_candles(
                symbol=symbol,
                interval=PRO_V2_HTF_INTERVAL,
                limit=120,
            )
        except Exception:
            htf_df = None

    result = pipeline.analyze(symbol=symbol, interval=interval)
    return diagnose_scan(
        result,
        timeframe=interval,
        min_confidence=min_confidence,
        htf_df=htf_df,
    )


def format_diagnostic_block(diag: ScanDiagnostic) -> str:
    """Format one scan in the user-requested layout."""
    check_map = {c.name: c for c in diag.checks}

    def line(label: str, key: str) -> str:
        check = check_map.get(key)
        if not check:
            return f"{label}: N/A"
        status = _pass_fail(check.passed)
        detail = f" ({check.detail})" if check.detail else ""
        return f"{label}: {status}{detail}"

    lines = [
        diag.symbol,
        f"Market regime: {diag.regime or 'Unknown'}",
        line("Trend", "Trend"),
        line("HTF bias", "HTF"),
        f"Market structure: {diag.structure}",
        line("BOS", "BOS"),
        line("CHOCH", "CHOCH"),
        line("Liquidity sweep", "Liquidity"),
        line("Order Block", "Order Block"),
        line("FVG", "FVG"),
        line("EMA filter", "EMA"),
        line("ADX", "ADX"),
        line("RSI", "RSI"),
        line("Volume", "Volume"),
        line("ATR", "ATR"),
        line("Regime gate", "Regime"),
        f"Confidence score: {diag.confidence:.1f}",
        f"Final decision: {diag.final_decision}",
    ]

    if diag.engine_signal == "WAIT" or not diag.would_alert:
        lines.append(f"Rejection reason: {diag.rejection_reason}")

    return "\n".join(lines)


def diagnose_scan_block(
    result: "AnalysisResult",
    *,
    timeframe: str,
    min_confidence: float | None = None,
    htf_df: pd.DataFrame | None = None,
) -> str:
    """Run diagnostics for one scan and return the formatted log block."""
    return format_diagnostic_block(
        diagnose_scan(
            result,
            timeframe=timeframe,
            min_confidence=min_confidence,
            htf_df=htf_df,
        )
    )


def _confluence_side_ok(
    *,
    hits: int,
    score: float,
    opposite_score: float,
) -> tuple[bool, str]:
    gap = score - opposite_score
    ok = (
        hits >= PRO_MIN_CONDITIONS
        and score >= PRO_MIN_CONFIDENCE
        and gap >= PRO_MIN_DIRECTION_GAP
    )
    detail = (
        f"hits={hits}/{PRO_MIN_CONDITIONS} "
        f"score={score:.1f}/{PRO_MIN_CONFIDENCE:.0f} "
        f"gap={gap:.1f}/{PRO_MIN_DIRECTION_GAP:.0f}"
    )
    return ok, detail


def _confluence_condition_pass(cond, direction: str) -> tuple[bool, str]:
    if direction == "BUY":
        ok = cond.aligned and cond.direction == "LONG"
    elif direction == "SELL":
        ok = cond.aligned and cond.direction == "SHORT"
    else:
        ok = cond.aligned
    detail = cond.reason
    if cond.aligned and cond.direction not in ("LONG", "SHORT"):
        detail = f"{cond.reason} (neutral — no directional score)"
    elif cond.aligned and not ok:
        detail = f"{cond.reason} (aligned {cond.direction}, need {direction})"
    return ok, detail


def _build_engine_gate_checks_v1(
    result: "AnalysisResult",
    ctx: MarketContext,
    diag: ScanDiagnostic,
    *,
    min_confidence: float,
) -> list[CheckResult]:
    signal = result.signal
    regime = ctx.regime or detect_regime_from_context(ctx)
    profile = build_regime_profile(regime)
    confluence = score_confluence(
        last=ctx.last,
        trend=ctx.trend,
        bos=ctx.bos,
        choch=ctx.choch,
        liquidity=ctx.liquidity,
        order_block=ctx.order_block,
        fvg=ctx.fvg,
        htf_trend=ctx.htf_trend,
        structure=ctx.structure,
        regime=regime,
        profile=profile,
    )
    long_ok, long_detail = _confluence_side_ok(
        hits=confluence.long_hits,
        score=confluence.long_score,
        opposite_score=confluence.short_score,
    )
    short_ok, short_detail = _confluence_side_ok(
        hits=confluence.short_hits,
        score=confluence.short_score,
        opposite_score=confluence.long_score,
    )
    picked, pick_conf, _ = pick_direction(
        confluence,
        min_conditions=PRO_MIN_CONDITIONS,
        min_confidence=PRO_MIN_CONFIDENCE,
        min_gap=PRO_MIN_DIRECTION_GAP,
    )
    engine_signal = signal.get("signal", "WAIT")
    engine_reason = signal.get("reasons", ["Unknown"])[0] if signal.get("reasons") else "Unknown"
    pick_detail = (
        f"selected={picked} confidence={pick_conf:.1f}"
        if picked
        else f"No side met thresholds (best {max(confluence.long_score, confluence.short_score):.1f})"
    )

    regime_ok, regime_detail = validate_regime_confirmations(
        regime,
        picked or diag.candidate_direction,
        confluence.conditions,
        trend=ctx.trend,
        htf_trend=ctx.htf_trend,
        bos=ctx.bos,
        choch=ctx.choch,
    )

    ready = SignalEnginePro._ready(ctx.last)
    engine_conf = float(signal.get("confidence", signal.get("confluence", 0)))
    diag_conf = diag.confidence
    confidence_detail = (
        f"engine={engine_conf:.1f} diagnostic={diag_conf:.1f} grade={diag.grade} "
        f"buy={float(signal.get('buy_confidence', 0)):.1f} "
        f"sell={float(signal.get('sell_confidence', 0)):.1f}"
    )
    confidence_pass = engine_signal in ("BUY", "SELL") and engine_conf >= PRO_MIN_CONFIDENCE
    if engine_signal == "WAIT" and diag_conf >= PRO_MIN_CONFIDENCE:
        confidence_pass = False
        confidence_detail += " (engine WAIT zeros confidence; diagnostic score shown)"

    tele_detail = (
        f"{diag.confidence:.1f} vs Telegram min {min_confidence:.0f}"
        if engine_signal in ("BUY", "SELL")
        else "N/A — engine WAIT"
    )

    return [
        CheckResult(
            "Indicators ready",
            ready,
            "All required indicators calculated"
            if ready
            else "One or more required indicators missing",
        ),
        CheckResult("Confluence BUY", long_ok, long_detail),
        CheckResult("Confluence SELL", short_ok, short_detail),
        CheckResult("Engine pick_direction", picked is not None, pick_detail),
        CheckResult(
            "Engine signal",
            engine_signal in ("BUY", "SELL"),
            f"signal={engine_signal} | {engine_reason}",
        ),
        CheckResult(
            "Engine regime",
            regime_ok,
            regime_detail
            + (" (engine stopped before this gate)" if engine_signal == "WAIT" else ""),
        ),
        CheckResult("Confidence threshold", confidence_pass, confidence_detail),
        CheckResult("Risk", diag.risk_ok, diag.risk_detail),
        CheckResult("Telegram gate", diag.would_alert, tele_detail),
    ]


def _build_engine_gate_checks_v2(
    result: "AnalysisResult",
    ctx: MarketContext,
    diag: ScanDiagnostic,
    *,
    min_confidence: float,
) -> list[CheckResult]:
    signal = result.signal
    direction = diag.candidate_direction
    narrative = pick_best_narrative(ctx)
    htf = evaluate_htf_bias(ctx)
    confirmations = run_confirmations(ctx, direction)
    regime_gates = run_regime_gates(ctx, direction)
    sl = ctx.swing_lows[-1]["price"] if ctx.swing_lows else None
    sh = ctx.swing_highs[-1]["price"] if ctx.swing_highs else None
    risk = RiskManagerV2.calculate(ctx, direction, swing_low=sl, swing_high=sh)
    rr = risk["rr"] if risk else 0
    grade, confidence = assign_grade(narrative, confirmations, htf, rr)
    grade_ok = grade_emits_signal(grade)
    engine_signal = signal.get("signal", "WAIT")
    engine_reason = signal.get("reasons", ["Unknown"])[0] if signal.get("reasons") else "Unknown"
    conf_ok = all(c.aligned for c in confirmations)
    conf_detail = "; ".join(
        f"{c.name}={'PASS' if c.aligned else 'FAIL'} ({c.reason})" for c in confirmations
    )
    regime_ok = all(g.passed for g in regime_gates)
    regime_detail = "; ".join(
        f"{g.name}={'PASS' if g.passed else 'FAIL'} ({g.reason})" for g in regime_gates
    )

    return [
        CheckResult(
            "Narrative",
            narrative.direction is not None,
            narrative.summary or "No complete setup narrative",
        ),
        CheckResult("HTF bias gate", htf_allows(direction, htf), htf.reason),
        CheckResult("Confirmations", conf_ok, conf_detail),
        CheckResult("Regime gates", regime_ok, regime_detail),
        CheckResult(
            "Grade",
            grade_ok,
            f"grade={grade} confidence={confidence:.1f}",
        ),
        CheckResult(
            "Engine signal",
            engine_signal in ("BUY", "SELL"),
            f"signal={engine_signal} | {engine_reason}",
        ),
        CheckResult("Risk", diag.risk_ok, diag.risk_detail),
        CheckResult(
            "Telegram gate",
            diag.would_alert,
            f"{diag.confidence:.1f} vs Telegram min {min_confidence:.0f}",
        ),
    ]


def format_gate_audit_block(
    result: "AnalysisResult",
    diag: ScanDiagnostic,
    *,
    timeframe: str,
    min_confidence: float | None = None,
    htf_df: pd.DataFrame | None = None,
) -> str:
    """Format PASS/FAIL audit for every decision gate in the pipeline."""
    min_confidence = min_confidence if min_confidence is not None else TELEGRAM_NOTIFY_MIN_CONFIDENCE
    signal = result.signal
    ctx = MarketContextBuilder.build(
        result.df,
        symbol=result.symbol,
        interval=timeframe,
        htf_df=htf_df,
        indicators_calculated=True,
    )

    lines = [
        f"=== Decision Gate Audit | {diag.symbol} | {diag.engine_version} | {timeframe}m ===",
        (
            f"Context | candidate={diag.candidate_direction} "
            f"trend={ctx.trend} structure={diag.structure} "
            f"regime={diag.regime or 'Unknown'} "
            f"htf={ctx.htf_trend}"
        ),
        "--- Setup filters (candidate direction) ---",
    ]

    for check in diag.checks:
        lines.append(f"GATE | {check.name} | {_pass_fail(check.passed)} | {check.detail}")

    if diag.engine_version == "v1":
        regime = ctx.regime or detect_regime_from_context(ctx)
        profile = build_regime_profile(regime)
        confluence = score_confluence(
            last=ctx.last,
            trend=ctx.trend,
            bos=ctx.bos,
            choch=ctx.choch,
            liquidity=ctx.liquidity,
            order_block=ctx.order_block,
            fvg=ctx.fvg,
            htf_trend=ctx.htf_trend,
            structure=ctx.structure,
            regime=regime,
            profile=profile,
        )
        lines.append("--- Confluence factors ---")
        for cond in confluence.conditions:
            ok, detail = _confluence_condition_pass(cond, diag.candidate_direction)
            lines.append(f"GATE | Confluence:{cond.name} | {_pass_fail(ok)} | {detail}")

        engine_checks = _build_engine_gate_checks_v1(
            result,
            ctx,
            diag,
            min_confidence=min_confidence,
        )
    else:
        engine_checks = _build_engine_gate_checks_v2(
            result,
            ctx,
            diag,
            min_confidence=min_confidence,
        )

    lines.append("--- Engine gates ---")
    for check in engine_checks:
        lines.append(f"GATE | {check.name} | {_pass_fail(check.passed)} | {check.detail}")

    failed_names = [c.name for c in diag.checks if not c.passed]
    failed_engine = [c.name for c in engine_checks if not c.passed]
    primary = failed_names[:3] + failed_engine[:3]
    engine_conf = float(signal.get("confidence", signal.get("confluence", 0)))
    lines.extend([
        "--- Summary ---",
        f"Primary blockers: {', '.join(primary) if primary else 'none'}",
        (
            f"Engine reported: signal={signal.get('signal', 'WAIT')} "
            f"confidence={engine_conf:.1f} "
            f"(diagnostic confidence={diag.confidence:.1f} grade={diag.grade})"
        ),
        f"Final decision: {diag.final_decision} | rejection={diag.rejection_reason}",
    ])
    return "\n".join(lines)


def log_decision_gate_audit(
    audit_logger: logging.Logger,
    result: "AnalysisResult",
    diag: ScanDiagnostic,
    *,
    timeframe: str,
    min_confidence: float | None = None,
    htf_df: pd.DataFrame | None = None,
) -> None:
    """Emit structured PASS/FAIL lines for every pipeline decision gate."""
    block = format_gate_audit_block(
        result,
        diag,
        timeframe=timeframe,
        min_confidence=min_confidence,
        htf_df=htf_df,
    )
    for line in block.splitlines():
        audit_logger.info(line)


def summarize_diagnostics(diagnostics: list[ScanDiagnostic]) -> str:
    """Build aggregate report from multiple scan diagnostics."""
    if not diagnostics:
        return "No diagnostics collected."

    n = len(diagnostics)
    engine = diagnostics[0].engine_version
    alerts = sum(1 for d in diagnostics if d.would_alert)
    engine_signals = sum(1 for d in diagnostics if d.engine_signal in ("BUY", "SELL"))
    telegram_blocks = sum(1 for d in diagnostics if d.telegram_blocked)

    fail_counts: dict[str, int] = {}
    for diag in diagnostics:
        for check in diag.failed_checks:
            fail_counts[check.name] = fail_counts.get(check.name, 0) + 1

    lines = [
        "# Signal Pipeline Diagnostic Report",
        "",
        f"- Engine: **{engine}**",
        f"- Symbols scanned: **{n}**",
        f"- Engine signals (BUY/SELL): **{engine_signals}**",
        f"- Telegram-eligible: **{alerts}**",
        f"- Blocked by Telegram confidence gate: **{telegram_blocks}**",
        "",
        "## Failure Frequency (checks that failed)",
        "",
    ]

    if fail_counts:
        for name, count in sorted(fail_counts.items(), key=lambda x: -x[1]):
            pct = count / n * 100
            lines.append(f"- **{name}**: {count}/{n} scans ({pct:.0f}%)")
    else:
        lines.append("- No check failures recorded (unexpected if no signals).")

    lines.extend(["", "## Per-Symbol Results", ""])
    for diag in diagnostics:
        lines.append("```")
        lines.append(format_diagnostic_block(diag))
        lines.append("```")
        lines.append("")

    lines.extend(["", "## Analysis", ""])
    lines.extend(_analysis_notes(diagnostics, fail_counts, engine))
    return "\n".join(lines)


def _analysis_notes(
    diagnostics: list[ScanDiagnostic],
    fail_counts: dict[str, int],
    engine: str,
) -> list[str]:
    notes: list[str] = []
    n = len(diagnostics)

    if not fail_counts:
        notes.append(
            "All individual checks passed on at least one side, yet no alerts fired. "
            "Inspect engine-level confluence/sequential gates and Telegram confidence threshold."
        )
        return notes

    top_fail = max(fail_counts, key=fail_counts.get)
    top_pct = fail_counts[top_fail] / n * 100

    notes.append(
        f"Primary blocker across scans: **{top_fail}** failed in "
        f"{fail_counts[top_fail]}/{n} scans ({top_pct:.0f}%)."
    )

    if engine == "v1":
        notes.append(
            f"PRO v1 requires **{PRO_MIN_CONDITIONS}** aligned conditions, "
            f"**{PRO_MIN_CONFIDENCE:.0f}** confidence, and **{PRO_MIN_DIRECTION_GAP:.0f}** "
            f"direction gap — all must pass simultaneously."
        )
        if fail_counts.get("Liquidity", 0) >= n * 0.8:
            notes.append(
                "**Liquidity sweeps are rare** on closed-bar detection (only triggers when "
                "current bar sweeps a 20-bar high/low and closes back inside). This is the "
                "most likely structural cause of zero signals — not a bug, but a strict filter."
            )
        if fail_counts.get("FVG", 0) >= n * 0.7 or fail_counts.get("Order Block", 0) >= n * 0.7:
            notes.append(
                "Price must be **within 0.3%** of an active FVG or order block zone. "
                "Wider proximity helps, but confluence may still fall short of 5 factors."
            )
        telegram_blocks = sum(1 for d in diagnostics if d.telegram_blocked)
        engine_hits = sum(1 for d in diagnostics if d.engine_signal in ("BUY", "SELL"))
        if engine_hits == 0:
            max_conf = max(d.confidence for d in diagnostics)
            notes.append(
                f"Best candidate confidence this scan: **{max_conf:.1f}**. "
                f"Engine threshold is {PRO_MIN_CONFIDENCE:.0f}; Telegram requires "
                f"{TELEGRAM_NOTIFY_MIN_CONFIDENCE:.0f}."
            )
            if max_conf >= PRO_MIN_CONFIDENCE and max_conf < TELEGRAM_NOTIFY_MIN_CONFIDENCE:
                notes.append(
                    "**Mismatch identified:** engine can emit at 65+ but Telegram requires 90. "
                    "Align `TELEGRAM_NOTIFY_MIN_CONFIDENCE` with `PRO_MIN_CONFIDENCE` or use "
                    "engine-grade gating instead of a flat 90 threshold."
                )
        elif telegram_blocks > 0:
            notes.append(
                f"{telegram_blocks} symbol(s) passed the engine but were blocked by the "
                f"Telegram confidence gate (≥{TELEGRAM_NOTIFY_MIN_CONFIDENCE:.0f})."
            )

    if engine == "v2":
        notes.append(
            f"PRO v2 requires a **complete sequential narrative** (HTF + sweep + displacement + "
            f"POI return + structure break + confirmation) plus grade ≥ **{PRO_V2_MIN_GRADE}**."
        )
        if fail_counts.get("HTF", 0) >= n * 0.6:
            notes.append(
                "HTF bias failure suggests higher-timeframe trend/structure is neutral or "
                "opposing both directions — continuation setups cannot start."
            )
        if fail_counts.get("Liquidity", 0) >= n * 0.7:
            notes.append(
                "Liquidity sweep step fails frequently. v2 accepts pool-based sweeps as fallback, "
                "but still requires price to have taken sell-side/buy-side pools — verify on lower timeframes."
            )

    notes.extend([
        "",
        "### Recommended fixes (do not lower confidence blindly)",
        "",
        "1. **Run this diagnostic on the VPS** after deploy — logs every scan cycle automatically.",
        "2. **Align Telegram gate with engine output** — if engine max confidence is 65–85, "
        f"set `TELEGRAM_NOTIFY_MIN_CONFIDENCE` to match engine grade mapping, not 90.",
        "3. **If Liquidity is top blocker** — consider requiring liquidity OR structure break "
        "(not both) for v1 confluence, or widen sweep lookback in a future engine change.",
        "4. **If using v2** — enable shadow mode: log v2 diagnostics while trading v1 until "
        "narrative completion rate is validated on live data.",
        "5. **Verify closed-bar timing** — scanners on forming bars may miss sweeps that "
        "complete on bar close; confirm `MarketContextBuilder` uses closed bars only.",
    ])

    return notes
