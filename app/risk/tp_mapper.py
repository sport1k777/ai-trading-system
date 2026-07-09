"""Liquidity-based take-profit mapping."""

from __future__ import annotations

import pandas as pd

from app.analysis.market_context import MarketContext
from app.analysis.pro_v2.liquidity_pools import detect_liquidity_pools


def map_take_profits(
    ctx: MarketContext,
    direction: str,
    entry: float,
    stop: float,
    tp1: float,
) -> tuple[float, float, float]:
    pools = detect_liquidity_pools(ctx)
    poc = ctx.last.get("poc")
    poc_val = float(poc) if poc is not None and pd.notna(poc) else None

    if direction == "BUY":
        tp2 = poc_val if poc_val and poc_val > entry else entry + abs(entry - stop) * 1.5
        buy_pools = pools.get("buy_side_pools") or []
        above = [p for p in buy_pools if p > entry]
        tp3 = min(above) if above else entry + abs(entry - stop) * 2.5
        tp2 = max(tp2, tp1)
        tp3 = max(tp3, tp2)
    else:
        tp2 = poc_val if poc_val and poc_val < entry else entry - abs(entry - stop) * 1.5
        sell_pools = pools.get("sell_side_pools") or []
        below = [p for p in sell_pools if p < entry]
        tp3 = max(below) if below else entry - abs(entry - stop) * 2.5
        tp2 = min(tp2, tp1)
        tp3 = min(tp3, tp2)

    return round(tp1, 2), round(tp2, 2), round(tp3, 2)
