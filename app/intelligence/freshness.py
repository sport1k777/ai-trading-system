"""Information freshness decay — old news must not score as breaking."""

from __future__ import annotations

import math

from app.config import (
    INTELLIGENCE_FRESHNESS_HALF_LIFE_MINUTES,
    INTELLIGENCE_MAX_NEWS_AGE_HOURS,
)


def freshness_weight(age_minutes: float, *, half_life_minutes: float | None = None) -> float:
    """Exponential decay: weight 1.0 at t=0, 0.5 at half-life."""
    if age_minutes < 0:
        age_minutes = 0.0
    half_life = half_life_minutes or INTELLIGENCE_FRESHNESS_HALF_LIFE_MINUTES
    if half_life <= 0:
        return 1.0
    return math.exp(-0.693147 * age_minutes / half_life)


def is_stale_for_signals(age_minutes: float) -> bool:
    """News older than configured max age is excluded from short-term signals."""
    return age_minutes > INTELLIGENCE_MAX_NEWS_AGE_HOURS * 60.0


def freshness_label(age_minutes: float | None) -> str:
    if age_minutes is None:
        return "unknown"
    if age_minutes < 60:
        return f"{age_minutes:.0f}m ago"
    if age_minutes < 1440:
        return f"{age_minutes / 60:.1f}h ago"
    return f"{age_minutes / 1440:.1f}d ago"
