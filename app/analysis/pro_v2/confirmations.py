"""Momentum and institutional confirmation filters."""

from __future__ import annotations

import pandas as pd

from app.analysis.market_context import MarketContext
from app.analysis.pro_v2.models import ConfirmationResult


def check_ema_stack(ctx: MarketContext, direction: str) -> ConfirmationResult:
    last = ctx.last
    close = float(last["close"])
    ema20, ema50, ema200 = float(last["ema20"]), float(last["ema50"]), float(last["ema200"])

    if direction == "BUY":
        aligned = ema20 > ema50 and close > ema50
        reason = "Bullish EMA stack" if aligned else "EMA stack not bullish"
    else:
        aligned = ema20 < ema50 and close < ema50
        reason = "Bearish EMA stack" if aligned else "EMA stack not bearish"

    return ConfirmationResult("EMA Stack", aligned, reason)


def check_rsi(ctx: MarketContext, direction: str) -> ConfirmationResult:
    rsi = float(ctx.last["rsi"])
    if direction == "BUY":
        aligned = 48 <= rsi <= 65
        reason = f"RSI momentum {rsi:.1f}" if aligned else f"RSI not bullish ({rsi:.1f})"
    else:
        aligned = 35 <= rsi <= 52
        reason = f"RSI momentum {rsi:.1f}" if aligned else f"RSI not bearish ({rsi:.1f})"
    return ConfirmationResult("RSI", aligned, reason)


def check_vwap(ctx: MarketContext, direction: str) -> ConfirmationResult:
    vwap = ctx.last.get("vwap")
    if pd.isna(vwap):
        return ConfirmationResult("VWAP", False, "VWAP unavailable")
    vwap = float(vwap)
    price = ctx.price
    if direction == "BUY":
        aligned = price >= vwap * 0.998
        reason = "Price at/above VWAP" if aligned else "Price below VWAP"
    else:
        aligned = price <= vwap * 1.002
        reason = "Price at/below VWAP" if aligned else "Price above VWAP"
    return ConfirmationResult("VWAP", aligned, reason)


def check_volume_profile(ctx: MarketContext, direction: str) -> ConfirmationResult:
    poc = ctx.last.get("poc")
    if pd.isna(poc):
        return ConfirmationResult("Volume Profile", False, "POC unavailable")
    poc = float(poc)
    price = ctx.price
    if direction == "BUY":
        aligned = price >= poc * 0.995
        reason = f"Price holding above POC {poc:.2f}" if aligned else f"Price below POC {poc:.2f}"
    else:
        aligned = price <= poc * 1.005
        reason = f"Price holding below POC {poc:.2f}" if aligned else f"Price above POC {poc:.2f}"
    return ConfirmationResult("Volume Profile", aligned, reason)


def run_confirmations(ctx: MarketContext, direction: str) -> list[ConfirmationResult]:
    return [
        check_ema_stack(ctx, direction),
        check_rsi(ctx, direction),
        check_vwap(ctx, direction),
        check_volume_profile(ctx, direction),
    ]
