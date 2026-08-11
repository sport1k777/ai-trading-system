"""Source reliability weighting."""

from __future__ import annotations

from app.intelligence.models import IntelligenceItem, ReliabilityTier

TIER_WEIGHT = {
    ReliabilityTier.OFFICIAL: 1.0,
    ReliabilityTier.REPUTABLE: 0.75,
    ReliabilityTier.ANALYST: 0.5,
    ReliabilityTier.SOCIAL: 0.25,
    ReliabilityTier.UNKNOWN: 0.1,
}


def weighted_sentiment(items: list[IntelligenceItem], freshness_weights: list[float]) -> float | None:
    if not items:
        return None
    num = 0.0
    den = 0.0
    for item, fw in zip(items, freshness_weights):
        w = TIER_WEIGHT.get(item.reliability, 0.1) * item.relevance * fw
        num += item.sentiment * w
        den += w
    if den <= 0:
        return None
    return max(-1.0, min(1.0, num / den))
