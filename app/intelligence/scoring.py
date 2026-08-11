"""Structured intelligence scoring with blockers — not a simple average."""

from __future__ import annotations

from typing import Optional

from app.config import (
    INTELLIGENCE_BLOCK_NEGATIVE_NEWS,
    INTELLIGENCE_WEIGHT_FUNDAMENTAL,
    INTELLIGENCE_WEIGHT_LIQUIDITY,
    INTELLIGENCE_WEIGHT_MOMENTUM,
    INTELLIGENCE_WEIGHT_NEWS,
    INTELLIGENCE_WEIGHT_ONCHAIN,
    INTELLIGENCE_WEIGHT_REGIME,
    INTELLIGENCE_WEIGHT_SOCIAL,
    INTELLIGENCE_WEIGHT_TECHNICAL,
)
from app.intelligence.market_regime import GlobalMarketRegime
from app.intelligence.models import IntelligenceScores, SymbolIntelligence
from app.pipeline import AnalysisResult


def score_candidate(
    result: AnalysisResult,
    intel: SymbolIntelligence,
    regime: GlobalMarketRegime,
    *,
    fast_scan_score: float = 0.0,
) -> IntelligenceScores:
    """Compute structured scores; blockers override composite."""
    signal = result.signal
    direction = signal.get("signal", "WAIT")

    technical = _technical_score(result)
    liquidity = _liquidity_score(intel, result)
    momentum = min(100.0, fast_scan_score * 4.0) if fast_scan_score else _momentum_score(result)
    regime_score = _regime_score(regime, direction)
    setup_quality = _setup_quality(result)
    risk = _risk_score(result, intel)

    scores = IntelligenceScores(
        symbol=result.symbol,
        technical_score=technical,
        regime_score=regime_score,
        liquidity_score=liquidity,
        momentum_score=momentum,
        news_score=_scale_optional(intel.news_score),
        social_score=_scale_optional(intel.social_score),
        fundamental_score=_scale_optional(intel.fundamental_score),
        onchain_score=_scale_optional(intel.onchain_score),
        setup_quality_score=setup_quality,
        risk_score=risk,
        sources_used=list(intel.available_sources),
        sources_unavailable=list(intel.unavailable_sources),
    )

    # Blockers — some information vetoes the setup entirely.
    for blocker in intel.blockers:
        scores.blockers.append(blocker)

    if INTELLIGENCE_BLOCK_NEGATIVE_NEWS and intel.news_score is not None:
        if intel.news_score <= -0.5 and direction == "BUY":
            scores.blockers.append("Blocking negative news contradicts LONG setup")
        if intel.news_score >= 0.5 and direction == "SELL":
            scores.blockers.append("Blocking positive news contradicts SHORT setup")

    if direction == "BUY" and not regime.altcoin_long_favorable and result.symbol != "BTCUSDT":
        scores.blockers.append(f"BTC regime unfavorable for LONG: {regime.summary}")
    if direction == "SELL" and not regime.altcoin_short_favorable and result.symbol != "BTCUSDT":
        scores.blockers.append(f"BTC regime unfavorable for SHORT: {regime.summary}")

    if intel.spread_pct is not None and intel.spread_pct > 0.5:
        scores.warnings.append(f"Wide spread {intel.spread_pct:.2f}%")

    # Composite — weighted only from available scores.
    parts: list[tuple[float, float]] = [
        (technical, INTELLIGENCE_WEIGHT_TECHNICAL),
        (regime_score, INTELLIGENCE_WEIGHT_REGIME),
        (liquidity, INTELLIGENCE_WEIGHT_LIQUIDITY),
        (momentum, INTELLIGENCE_WEIGHT_MOMENTUM),
        (setup_quality, 0.15),
    ]
    if scores.news_score is not None:
        parts.append((scores.news_score, INTELLIGENCE_WEIGHT_NEWS))
    if scores.social_score is not None:
        parts.append((scores.social_score, INTELLIGENCE_WEIGHT_SOCIAL))
    if scores.fundamental_score is not None:
        parts.append((scores.fundamental_score, INTELLIGENCE_WEIGHT_FUNDAMENTAL))
    if scores.onchain_score is not None:
        parts.append((scores.onchain_score, INTELLIGENCE_WEIGHT_ONCHAIN))

    total_w = sum(w for _, w in parts)
    scores.composite_score = sum(v * w for v, w in parts) / total_w if total_w else 0.0

    # Confidence adjustment from intelligence (-10..+10)
    adj = 0.0
    if scores.news_score is not None:
        adj += (scores.news_score - 50) / 10.0
    if scores.fundamental_score is not None:
        adj += (scores.fundamental_score - 50) / 15.0
    if regime.risk_mode == "RISK_ON" and direction == "BUY":
        adj += 2.0
    if regime.risk_mode == "RISK_OFF" and direction == "SELL":
        adj += 2.0
    scores.confidence_adjustment = max(-10.0, min(10.0, adj))

    scores.key_reasons = _build_reasons(result, intel, regime, scores)
    if intel.items:
        ages = [i.age_minutes for i in intel.items if i.published_at or i.fetched_at]
        if ages:
            scores.data_freshness_minutes = min(ages)
    return scores


def _technical_score(result: AnalysisResult) -> float:
    conf = float(result.signal.get("confidence", result.signal.get("confluence", 0)))
    return min(100.0, conf)


def _liquidity_score(intel: SymbolIntelligence, result: AnalysisResult) -> float:
    score = 50.0
    if intel.turnover_24h:
        if intel.turnover_24h > 50_000_000:
            score += 30
        elif intel.turnover_24h > 5_000_000:
            score += 15
    if intel.spread_pct is not None:
        if intel.spread_pct < 0.05:
            score += 20
        elif intel.spread_pct > 0.3:
            score -= 25
    vr = float(result.df.iloc[-1].get("volume_ratio", 1))
    if vr >= 1.2:
        score += 10
    return max(0.0, min(100.0, score))


def _momentum_score(result: AnalysisResult) -> float:
    last = result.df.iloc[-1]
    adx = float(last.get("adx", 0))
    rsi = float(last.get("rsi", 50))
    base = min(100.0, adx * 2.5)
    if 40 <= rsi <= 60:
        base += 5
    return base


def _regime_score(regime: GlobalMarketRegime, direction: str) -> float:
    if direction not in ("BUY", "SELL"):
        return 50.0
    if direction == "BUY" and regime.altcoin_long_favorable:
        return 80.0 if regime.risk_mode == "RISK_ON" else 60.0
    if direction == "SELL" and regime.altcoin_short_favorable:
        return 80.0 if regime.risk_mode == "RISK_OFF" else 60.0
    return 30.0


def _setup_quality(result: AnalysisResult) -> float:
    risk = result.risk
    if not risk:
        return 0.0
    rr1 = float(risk.get("rr_tp1", risk.get("rr", 0)))
    return min(100.0, 40 + rr1 * 20)


def _risk_score(result: AnalysisResult, intel: SymbolIntelligence) -> float:
    score = 70.0
    if intel.blockers:
        score -= 40
    for w in intel.warnings:
        if "spread" in w.lower():
            score -= 15
    return max(0.0, min(100.0, score))


def _scale_optional(val: Optional[float]) -> Optional[float]:
    if val is None:
        return None
    return max(0.0, min(100.0, (val + 1.0) * 50.0))


def _build_reasons(
    result: AnalysisResult,
    intel: SymbolIntelligence,
    regime: GlobalMarketRegime,
    scores: IntelligenceScores,
) -> list[str]:
    reasons: list[str] = []
    signal = result.signal
    if signal.get("narrative"):
        reasons.append(str(signal["narrative"])[:80])
    reasons.append(f"BTC regime: {regime.summary[:60]}")
    if intel.news_score is not None:
        label = "positive" if intel.news_score > 0.1 else ("negative" if intel.news_score < -0.1 else "neutral")
        reasons.append(f"News sentiment: {label} ({intel.news_score:+.2f})")
    elif "news_rss" in str(intel.unavailable_sources):
        reasons.append("News: unavailable")
    if intel.social_score is None:
        reasons.append("Social/X: unavailable")
    if intel.onchain_score is None:
        reasons.append("On-chain: unavailable")
    if intel.funding_rate is not None:
        reasons.append(f"Funding rate: {intel.funding_rate:.6f}")
    return reasons[:6]
