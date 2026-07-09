"""Displacement candle detection."""

from __future__ import annotations

import pandas as pd

from app.analysis.market_context import MarketContext


def detect_displacement(
    ctx: MarketContext,
    direction: str,
    *,
    atr_mult: float = 1.3,
    lookback: int = 5,
) -> tuple[bool, str]:
    df = ctx.analysis_df
    if len(df) < lookback + 2:
        return False, "Insufficient bars for displacement"

    atr = ctx.atr
    if atr <= 0:
        return False, "ATR unavailable"

    recent = df.iloc[-(lookback + 1) : -1]
    for i in range(len(recent) - 1, -1, -1):
        bar = recent.iloc[i]
        body = abs(float(bar["close"]) - float(bar["open"]))
        if body < atr_mult * atr:
            continue
        if direction == "BUY" and bar["close"] > bar["open"]:
            return True, f"Bullish displacement (body {body:.2f} > {atr_mult}×ATR)"
        if direction == "SELL" and bar["close"] < bar["open"]:
            return True, f"Bearish displacement (body {body:.2f} > {atr_mult}×ATR)"

    return False, "No displacement candle in lookback"
