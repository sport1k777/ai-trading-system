"""Liquidity-based take-profit mapping — delegates to trade_plan_engine."""

from __future__ import annotations

from app.analysis.market_context import MarketContext
from app.risk.trade_plan_engine import build_trade_plan


def map_take_profits(
    ctx: MarketContext,
    direction: str,
    entry: float,
    stop: float,
    primary_tp: float,
) -> tuple[float, float, float] | None:
    """Build structural TP ladder via the authoritative trade-plan engine.

    ``primary_tp`` is retained for API compatibility but is not forced onto the ladder.
    """
    sl = ctx.swing_lows[-1]["price"] if ctx.swing_lows else None
    sh = ctx.swing_highs[-1]["price"] if ctx.swing_highs else None
    plan = build_trade_plan(ctx, direction, swing_low=sl, swing_high=sh)
    if not plan:
        return None
    return plan["tp1"], plan["tp2"], plan["tp3"]
