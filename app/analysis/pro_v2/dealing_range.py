"""Premium / discount and dealing range for PRO V2."""

from __future__ import annotations

from app.analysis.market_context import MarketContext
from app.analysis.pro_v2.models import DealingRange, Direction


def compute_dealing_range(ctx: MarketContext) -> DealingRange:
    view = ctx.view
    high = float(view["high"].max())
    low = float(view["low"].min())
    equilibrium = (high + low) / 2
    price = ctx.price
    range_size = high - low

    if range_size <= 0:
        return DealingRange(high, low, equilibrium, "equilibrium", "Flat dealing range")

    pct = (price - low) / range_size * 100
    if pct <= 45:
        zone = "discount"
        reason = f"Price in discount ({pct:.0f}% of range)"
    elif pct >= 55:
        zone = "premium"
        reason = f"Price in premium ({pct:.0f}% of range)"
    else:
        zone = "equilibrium"
        reason = f"Price near equilibrium ({pct:.0f}% of range)"

    return DealingRange(high=high, low=low, equilibrium=equilibrium, zone=zone, reason=reason)


def zone_allows(direction: Direction, dealing: DealingRange) -> bool:
    if direction == "LONG":
        return dealing.zone in ("discount", "equilibrium")
    if direction == "SHORT":
        return dealing.zone in ("premium", "equilibrium")
    return False
