"""Liquidity-based take-profit mapping."""

from __future__ import annotations

import pandas as pd

from app.analysis.market_context import MarketContext


def _dedupe_sorted(levels: list[float], entry: float, *, min_sep_pct: float = 0.0005) -> list[float]:
    """Drop near-duplicate prices while preserving order."""
    distinct: list[float] = []
    for price in levels:
        if not distinct:
            distinct.append(price)
            continue
        if all(abs(price - existing) / max(entry, 1e-9) > min_sep_pct for existing in distinct):
            distinct.append(price)
    return distinct


def _extend_ladder(
    levels: list[float],
    *,
    direction: str,
    entry: float,
    risk: float,
    minimum: int = 3,
) -> list[float]:
    """Pad the ladder with R-multiple targets when fewer than three distinct levels exist."""
    if risk <= 0:
        return levels

    result = list(levels)
    multipliers = (1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0)
    for mult in multipliers:
        if len(result) >= minimum:
            break
        candidate = entry + mult * risk if direction == "BUY" else entry - mult * risk
        if direction == "BUY" and candidate <= entry:
            continue
        if direction == "SELL" and candidate >= entry:
            continue
        result = _dedupe_sorted(result + [candidate], entry)
    return result


def map_take_profits(
    ctx: MarketContext,
    direction: str,
    entry: float,
    stop: float,
    primary_tp: float,
) -> tuple[float, float, float]:
    """Build a three-step TP ladder: nearest valid target first, then second, then third.

    ``primary_tp`` is the RR-based target from RiskManager (e.g. 2.2R). It remains
    on the ladder but is not forced to be TP1 — closer structural targets come first.
    """
    from app.analysis.pro_v2.liquidity_pools import detect_liquidity_pools

    risk = abs(entry - stop)
    pools = detect_liquidity_pools(ctx)
    poc = ctx.last.get("poc")
    poc_val = float(poc) if poc is not None and pd.notna(poc) else None

    candidates: list[float] = [primary_tp]

    if poc_val is not None:
        candidates.append(poc_val)

    if direction == "BUY":
        candidates.extend(p for p in (pools.get("buy_side_pools") or []) if p > entry)
        candidates.extend(entry + mult * risk for mult in (1.5, 2.0, 2.5))
        if ctx.swing_highs:
            candidates.append(float(ctx.swing_highs[-1]["price"]))
        valid = sorted(p for p in candidates if p > entry)
    else:
        candidates.extend(p for p in (pools.get("sell_side_pools") or []) if p < entry)
        candidates.extend(entry - mult * risk for mult in (1.5, 2.0, 2.5))
        if ctx.swing_lows:
            candidates.append(float(ctx.swing_lows[-1]["price"]))
        valid = sorted((p for p in candidates if p < entry), reverse=True)

    ladder = _extend_ladder(
        _dedupe_sorted(valid, entry),
        direction=direction,
        entry=entry,
        risk=risk,
        minimum=3,
    )

    tp1, tp2, tp3 = ladder[0], ladder[1], ladder[2]
    return round(tp1, 2), round(tp2, 2), round(tp3, 2)
