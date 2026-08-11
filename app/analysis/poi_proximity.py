"""Shared POI (Order Block / FVG) proximity checks."""

from __future__ import annotations

PROXIMITY_PCT = 0.003  # 0.3% tolerance beyond zone boundaries


def near_zone(
    price: float,
    low: float,
    high: float,
    *,
    pct: float = PROXIMITY_PCT,
) -> bool:
    """True when price is inside the zone or within pct of either boundary."""
    zone_low = min(low, high)
    zone_high = max(low, high)
    tol_low = zone_low * (1 - pct)
    tol_high = zone_high * (1 + pct)
    return tol_low <= price <= tol_high


def near_bullish_poi(price: float, low: float, high: float, *, pct: float | None = None) -> bool:
    return near_zone(price, low, high, pct=pct if pct is not None else PROXIMITY_PCT)


def near_bearish_poi(price: float, low: float, high: float, *, pct: float | None = None) -> bool:
    return near_zone(price, low, high, pct=pct if pct is not None else PROXIMITY_PCT)
