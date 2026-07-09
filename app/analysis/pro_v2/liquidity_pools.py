"""Liquidity pool detection (equal highs / equal lows)."""

from __future__ import annotations

from app.analysis.market_context import MarketContext


def _cluster_levels(levels: list[float], tolerance_pct: float = 0.15) -> list[float]:
    if not levels:
        return []
    levels = sorted(levels)
    clusters: list[list[float]] = [[levels[0]]]
    for lvl in levels[1:]:
        ref = clusters[-1][-1]
        if ref and abs(lvl - ref) / ref * 100 <= tolerance_pct:
            clusters[-1].append(lvl)
        else:
            clusters.append([lvl])
    return [sum(c) / len(c) for c in clusters if len(c) >= 2]


def detect_liquidity_pools(ctx: MarketContext, lookback: int = 40) -> dict:
    view = ctx.view.iloc[-lookback:]
    highs = view["high"].astype(float).tolist()
    lows = view["low"].astype(float).tolist()
    price = ctx.price

    buy_side = _cluster_levels(highs[-20:])
    sell_side = _cluster_levels(lows[-20:])

    nearest_buy = min(buy_side, key=lambda x: abs(x - price)) if buy_side else None
    nearest_sell = min(sell_side, key=lambda x: abs(x - price)) if sell_side else None

    return {
        "buy_side_pools": buy_side,
        "sell_side_pools": sell_side,
        "nearest_buy_side": nearest_buy,
        "nearest_sell_side": nearest_sell,
    }


def liquidity_swept_recently(ctx: MarketContext, direction: str, bars: int = 8) -> tuple[bool, str]:
    liq = ctx.liquidity
    if liq:
        if direction == "BUY" and liq.get("type") == "SELL_SIDE_SWEEP":
            return True, f"Sell-side sweep at {liq['level']:.2f}"
        if direction == "SELL" and liq.get("type") == "BUY_SIDE_SWEEP":
            return True, f"Buy-side sweep at {liq['level']:.2f}"

    pools = detect_liquidity_pools(ctx)
    price = ctx.price
    if direction == "BUY" and pools["sell_side_pools"]:
        level = min(pools["sell_side_pools"])
        if price > level:
            return True, f"Price above sell-side pool {level:.2f}"
    if direction == "SELL" and pools["buy_side_pools"]:
        level = max(pools["buy_side_pools"])
        if price < level:
            return True, f"Price below buy-side pool {level:.2f}"

    return False, "No recent liquidity sweep"
