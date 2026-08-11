"""Adaptive market regime detection and confirmation profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pandas as pd

if TYPE_CHECKING:
    from app.analysis.market_context import MarketContext
from app.analysis.pro.models import ConditionResult
from app.config import (
    MIN_ADX,
    PRO_CONDITION_WEIGHTS,
    PRO_MIN_CONFIDENCE,
    REGIME_HIGH_VOL_ATR_PCT,
    REGIME_LOW_VOL_ATR_PCT,
    REGIME_LOW_VOL_TP_R_MULT,
    REGIME_POI_TOLERANCE_HIGH,
    REGIME_POI_TOLERANCE_LOW,
    REGIME_STRONG_ADX,
    REGIME_WEAK_ADX,
)

TrendRegime = Literal["strong_trend", "weak_trend", "range"]
VolatilityRegime = Literal["high", "normal", "low"]


@dataclass(frozen=True)
class MarketRegime:
    trend_regime: TrendRegime
    volatility_regime: VolatilityRegime
    adx: float = 0.0
    atr_pct: float = 0.0
    reason: str = ""

    @property
    def label(self) -> str:
        trend = {
            "strong_trend": "Strong Trend",
            "weak_trend": "Weak Trend",
            "range": "Range",
        }[self.trend_regime]
        if self.volatility_regime == "high":
            return f"{trend} + High Volatility"
        if self.volatility_regime == "low":
            return f"{trend} + Low Volatility"
        return trend


@dataclass(frozen=True)
class RegimeProfile:
    weights: dict[str, float]
    atr_min: float
    atr_max: float
    poi_tolerance_pct: float
    tp_r_mult: float
    stop_mult_factor: float


def detect_market_regime(
    *,
    last: pd.Series,
    trend: str,
    structure: str,
    htf_trend: str | None = None,
) -> MarketRegime:
    adx = float(last.get("adx", 0) or 0)
    atr_pct = float(last.get("atr_pct", 0) or 0)

    if atr_pct >= REGIME_HIGH_VOL_ATR_PCT:
        vol: VolatilityRegime = "high"
    elif 0 < atr_pct <= REGIME_LOW_VOL_ATR_PCT:
        vol = "low"
    else:
        vol = "normal"

    directional = trend in ("BULLISH", "BEARISH") and structure in ("UPTREND", "DOWNTREND")

    if adx >= REGIME_STRONG_ADX and directional:
        trend_regime: TrendRegime = "strong_trend"
        reason = f"ADX {adx:.1f} with directional trend/structure"
    elif adx >= REGIME_WEAK_ADX and (directional or structure in ("UPTREND", "DOWNTREND")):
        trend_regime = "weak_trend"
        reason = f"ADX {adx:.1f} moderate trend"
    else:
        trend_regime = "range"
        reason = f"ADX {adx:.1f} / structure {structure} implies range"

    if htf_trend and htf_trend != "SIDEWAYS" and trend_regime == "range":
        trend_regime = "weak_trend"
        reason += f"; HTF {htf_trend} upgrades to weak trend"

    return MarketRegime(
        trend_regime=trend_regime,
        volatility_regime=vol,
        adx=adx,
        atr_pct=atr_pct,
        reason=reason,
    )


def detect_regime_from_context(ctx: MarketContext) -> MarketRegime:
    htf = ctx.htf_trend if ctx.htf_df is not None else None
    return detect_market_regime(
        last=ctx.last,
        trend=ctx.trend,
        structure=ctx.structure,
        htf_trend=htf,
    )


def build_regime_profile(regime: MarketRegime) -> RegimeProfile:
    weights = dict(PRO_CONDITION_WEIGHTS)

    if regime.trend_regime == "strong_trend":
        weights["structure"] *= 1.35
        weights["ema_trend"] *= 1.25
        weights["liquidity"] *= 0.85
    elif regime.trend_regime == "weak_trend":
        weights["structure"] *= 1.1
        weights["liquidity"] *= 0.95
    else:  # range
        weights["structure"] *= 0.65
        weights["liquidity"] *= 1.45
        weights["fvg"] *= 1.1
        weights["order_block"] *= 1.1

    atr_min, atr_max = 0.15, 5.0
    poi_tol = 0.003
    tp_r_mult = 1.0
    stop_mult_factor = 1.0

    if regime.volatility_regime == "high":
        atr_max = 8.0
        poi_tol = REGIME_POI_TOLERANCE_HIGH
    elif regime.volatility_regime == "low":
        atr_min = 0.10
        atr_max = 3.5
        poi_tol = REGIME_POI_TOLERANCE_LOW
        tp_r_mult = REGIME_LOW_VOL_TP_R_MULT
        stop_mult_factor = 0.85

    return RegimeProfile(
        weights=weights,
        atr_min=atr_min,
        atr_max=atr_max,
        poi_tolerance_pct=poi_tol,
        tp_r_mult=tp_r_mult,
        stop_mult_factor=stop_mult_factor,
    )


def is_volatility_tradeable_regime(last: pd.Series, profile: RegimeProfile) -> tuple[bool, str]:
    atr_pct = float(last.get("atr_pct", 0.0))
    if pd.isna(atr_pct) or atr_pct <= 0:
        return False, "ATR data unavailable"
    if profile.atr_min <= atr_pct <= profile.atr_max:
        return True, f"Tradeable volatility ({atr_pct:.2f}% ATR)"
    return False, f"Volatility out of tradeable range ({atr_pct:.2f}% ATR)"


def _cond_map(conditions: list[ConditionResult]) -> dict[str, ConditionResult]:
    return {c.name: c for c in conditions}


def _aligned_for_direction(cond: ConditionResult | None, direction: str) -> bool:
    if not cond or not cond.aligned:
        return False
    side = "LONG" if direction == "BUY" else "SHORT"
    return cond.direction == side


def validate_regime_confirmations(
    regime: MarketRegime,
    direction: str,
    conditions: list[ConditionResult],
    *,
    trend: str,
    htf_trend: str,
    bos: str,
    choch: str,
) -> tuple[bool, str]:
    """Adaptive confirmation gates — filters adapt, confidence thresholds do not."""
    by_name = _cond_map(conditions)
    ema = by_name.get("EMA Trend")
    adx = by_name.get("ADX Trend")
    liquidity = by_name.get("Liquidity Sweep")

    has_bos = (direction == "BUY" and bos == "BULLISH_BOS") or (
        direction == "SELL" and bos == "BEARISH_BOS"
    )
    has_choch = (direction == "BUY" and choch == "BULLISH_CHOCH") or (
        direction == "SELL" and choch == "BEARISH_CHOCH"
    )
    htf_ok = (direction == "BUY" and htf_trend == "BULLISH") or (
        direction == "SELL" and htf_trend == "BEARISH"
    )
    if not htf_ok and trend in ("BULLISH", "BEARISH"):
        htf_ok = (direction == "BUY" and trend == "BULLISH") or (
            direction == "SELL" and trend == "BEARISH"
        )

    if regime.trend_regime == "strong_trend":
        if not has_bos:
            return False, "Strong Trend requires BOS"
        if not htf_ok:
            return False, "Strong Trend requires HTF alignment"
        if not _aligned_for_direction(ema, direction):
            return False, "Strong Trend requires EMA confirmation"
        if not _aligned_for_direction(adx, direction) and not (adx and adx.aligned):
            return False, f"Strong Trend requires ADX (min {MIN_ADX:.0f})"
        return True, "Strong Trend confirmations satisfied"

    if regime.trend_regime == "weak_trend":
        if not (has_bos or has_choch):
            return False, "Weak Trend requires BOS or CHOCH"
        if not htf_ok:
            return False, "Weak Trend requires HTF alignment"
        return True, "Weak Trend confirmations satisfied"

    # Range regime
    if not (_aligned_for_direction(liquidity, direction) or has_choch):
        return False, "Range requires liquidity sweep or CHOCH"
    if regime.volatility_regime == "low":
        return True, "Range confirmations satisfied (ADX not required in low volatility)"
    if _aligned_for_direction(adx, direction):
        return True, "Range confirmations satisfied"
    return True, "Range confirmations satisfied (ADX optional)"


def estimate_win_rate(confidence: float, regime: MarketRegime) -> float:
    """Heuristic win-rate estimate for reporting (not used in signal gating)."""
    if confidence < PRO_MIN_CONFIDENCE:
        base = 0.32 + confidence * 0.004
    else:
        base = 0.48 + (confidence - 65) * 0.006

    trend_bonus = {
        "strong_trend": 0.09,
        "weak_trend": 0.04,
        "range": 0.01,
    }[regime.trend_regime]
    vol_bonus = {"high": -0.02, "normal": 0.0, "low": 0.02}[regime.volatility_regime]
    return round(min(0.75, max(0.25, base + trend_bonus + vol_bonus)), 3)
