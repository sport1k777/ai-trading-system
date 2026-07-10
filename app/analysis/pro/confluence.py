"""Confluence aggregation for Signal Engine PRO."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.analysis.market_regime import RegimeProfile, build_regime_profile
from app.analysis.pro.conditions import evaluate_all
from app.analysis.pro.models import ConfluenceScore, ConditionResult
from app.config import PRO_CONDITION_WEIGHTS

if TYPE_CHECKING:
    from app.analysis.market_regime import MarketRegime


def score_confluence(
    *,
    last,
    trend: str,
    bos: str,
    choch: str,
    liquidity: dict | None,
    order_block: dict | None,
    fvg: dict | None,
    weights: dict[str, float] | None = None,
    htf_trend: str = "SIDEWAYS",
    regime: Optional[MarketRegime] = None,
    profile: Optional[RegimeProfile] = None,
) -> ConfluenceScore:
    active_profile = profile or (build_regime_profile(regime) if regime else None)
    active_weights = weights or (active_profile.weights if active_profile else PRO_CONDITION_WEIGHTS)

    poi_tol = active_profile.poi_tolerance_pct if active_profile else None
    atr_min = active_profile.atr_min if active_profile else 0.15
    atr_max = active_profile.atr_max if active_profile else 5.0

    conditions = evaluate_all(
        last=last,
        trend=trend,
        bos=bos,
        choch=choch,
        liquidity=liquidity,
        order_block=order_block,
        fvg=fvg,
        weights=active_weights,
        htf_trend=htf_trend,
        poi_tolerance_pct=poi_tol,
        atr_min=atr_min,
        atr_max=atr_max,
    )

    long_score = short_score = 0.0
    long_hits = short_hits = 0
    long_reasons: list[str] = []
    short_reasons: list[str] = []

    for cond in conditions:
        if not cond.aligned:
            continue
        if cond.direction == "LONG":
            long_score += cond.weight
            long_hits += 1
            long_reasons.append(f"{cond.name}: {cond.reason}")
        elif cond.direction == "SHORT":
            short_score += cond.weight
            short_hits += 1
            short_reasons.append(f"{cond.name}: {cond.reason}")

    total_weight = sum(active_weights.values()) or 1.0
    return ConfluenceScore(
        long_score=round(long_score / total_weight * 100, 1),
        short_score=round(short_score / total_weight * 100, 1),
        long_hits=long_hits,
        short_hits=short_hits,
        conditions=conditions,
        long_reasons=long_reasons,
        short_reasons=short_reasons,
    )


def pick_direction(
    score: ConfluenceScore,
    *,
    min_conditions: int,
    min_confidence: float,
    min_gap: float,
) -> tuple[str | None, float, list[str]]:
    long_ok = (
        score.long_hits >= min_conditions
        and score.long_score >= min_confidence
        and score.long_score >= score.short_score + min_gap
    )
    short_ok = (
        score.short_hits >= min_conditions
        and score.short_score >= min_confidence
        and score.short_score >= score.long_score + min_gap
    )

    if long_ok and not short_ok:
        return "BUY", score.long_score, score.long_reasons
    if short_ok and not long_ok:
        return "SELL", score.short_score, score.short_reasons
    if long_ok and short_ok:
        if score.long_score > score.short_score:
            return "BUY", score.long_score, score.long_reasons
        if score.short_score > score.long_score:
            return "SELL", score.short_score, score.short_reasons
    return None, max(score.long_score, score.short_score), []


def build_explanation(
    direction: str | None,
    confidence: float,
    reasons: list[str],
    score: ConfluenceScore,
    *,
    min_conditions: int,
    min_confidence: float,
) -> str:
    side = "LONG" if direction == "BUY" else "SHORT" if direction == "SELL" else "NO TRADE"
    lines = [
        f"Signal Engine PRO — {side}",
        f"Confidence: {confidence:.1f}/100",
        f"Aligned conditions: {score.long_hits} long / {score.short_hits} short "
        f"(minimum {min_conditions} required, threshold {min_confidence:.0f})",
    ]
    if reasons:
        lines.append("Confluence:")
        lines.extend(f"- {r}" for r in reasons)
    else:
        lines.append("Confluence: insufficient multi-factor alignment.")
    return "\n".join(lines)


def conditions_to_feature_scores(conditions: list[ConditionResult]) -> list[dict]:
    """Map PRO conditions to the legacy feature_scores schema for downstream tooling."""
    rows: list[dict] = []
    for cond in conditions:
        buy = sell = 50.0
        if cond.aligned and cond.direction == "LONG":
            buy = 80.0
        elif cond.aligned and cond.direction == "SHORT":
            sell = 80.0
        rows.append(
            {
                "name": cond.name,
                "buy_score": buy,
                "sell_score": sell,
                "reason": cond.reason,
            }
        )
    return rows
