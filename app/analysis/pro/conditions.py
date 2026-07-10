"""Individual confluence condition evaluators for Signal Engine PRO."""

from __future__ import annotations

import pandas as pd

from app.analysis.poi_proximity import near_bearish_poi, near_bullish_poi
from app.analysis.pro.models import ConditionResult


def evaluate_structure(bos: str, choch: str, *, weight: float) -> ConditionResult:
    if bos == "BULLISH_BOS" or choch == "BULLISH_CHOCH":
        label = "Bullish BOS" if bos == "BULLISH_BOS" else "Bullish CHOCH"
        return ConditionResult(
            "Market Structure",
            "LONG",
            True,
            weight,
            f"{label} confirms upside structure break",
        )
    if bos == "BEARISH_BOS" or choch == "BEARISH_CHOCH":
        label = "Bearish BOS" if bos == "BEARISH_BOS" else "Bearish CHOCH"
        return ConditionResult(
            "Market Structure",
            "SHORT",
            True,
            weight,
            f"{label} confirms downside structure break",
        )
    return ConditionResult(
        "Market Structure",
        "NEUTRAL",
        False,
        weight,
        "No bullish or bearish BOS/CHOCH confirmation",
    )


def evaluate_fvg(fvg: dict | None, price: float, *, weight: float) -> ConditionResult:
    if not fvg:
        return ConditionResult("Fair Value Gap", "NEUTRAL", False, weight, "No active FVG")

    top, bottom = float(fvg["top"]), float(fvg["bottom"])
    if fvg["type"] == "BULLISH" and near_bullish_poi(price, bottom, top):
        return ConditionResult(
            "Fair Value Gap",
            "LONG",
            True,
            weight,
            f"Price within 0.3% of bullish FVG ({bottom:.2f}–{top:.2f})",
        )
    if fvg["type"] == "BEARISH" and near_bearish_poi(price, bottom, top):
        return ConditionResult(
            "Fair Value Gap",
            "SHORT",
            True,
            weight,
            f"Price within 0.3% of bearish FVG ({bottom:.2f}–{top:.2f})",
        )
    return ConditionResult(
        "Fair Value Gap",
        "NEUTRAL",
        False,
        weight,
        f"Active {fvg['type'].lower()} FVG not engaged by price",
    )


def evaluate_order_block(
    order_block: dict | None,
    price: float,
    *,
    weight: float,
) -> ConditionResult:
    if not order_block:
        return ConditionResult("Order Block", "NEUTRAL", False, weight, "No active order block")

    bullish = order_block.get("bullish")
    if bullish and near_bullish_poi(price, bullish["low"], bullish["high"]):
        return ConditionResult(
            "Order Block",
            "LONG",
            True,
            weight,
            f"Price within 0.3% of bullish OB ({bullish['low']:.2f}–{bullish['high']:.2f})",
        )

    bearish = order_block.get("bearish")
    if bearish and near_bearish_poi(price, bearish["low"], bearish["high"]):
        return ConditionResult(
            "Order Block",
            "SHORT",
            True,
            weight,
            f"Price within 0.3% of bearish OB ({bearish['low']:.2f}–{bearish['high']:.2f})",
        )

    return ConditionResult(
        "Order Block",
        "NEUTRAL",
        False,
        weight,
        "Order blocks present but price outside OB zones",
    )


def evaluate_liquidity(liquidity: dict | None, *, weight: float) -> ConditionResult:
    if not liquidity:
        return ConditionResult(
            "Liquidity Sweep",
            "NEUTRAL",
            False,
            weight,
            "No liquidity sweep detected",
        )

    if liquidity["type"] == "SELL_SIDE_SWEEP":
        return ConditionResult(
            "Liquidity Sweep",
            "LONG",
            True,
            weight,
            f"Sell-side liquidity swept at {liquidity['level']:.2f}",
        )
    if liquidity["type"] == "BUY_SIDE_SWEEP":
        return ConditionResult(
            "Liquidity Sweep",
            "SHORT",
            True,
            weight,
            f"Buy-side liquidity swept at {liquidity['level']:.2f}",
        )

    return ConditionResult(
        "Liquidity Sweep",
        "NEUTRAL",
        False,
        weight,
        "Liquidity event not directional",
    )


def evaluate_ema_trend(trend: str, last: pd.Series, *, weight: float) -> ConditionResult:
    close = float(last["close"])
    ema50 = float(last["ema50"])

    if trend == "BULLISH" and close > ema50:
        return ConditionResult(
            "EMA Trend",
            "LONG",
            True,
            weight,
            "Bullish EMA stack with price above EMA50",
        )
    if trend == "BEARISH" and close < ema50:
        return ConditionResult(
            "EMA Trend",
            "SHORT",
            True,
            weight,
            "Bearish EMA stack with price below EMA50",
        )
    return ConditionResult(
        "EMA Trend",
        "NEUTRAL",
        False,
        weight,
        f"Trend is {trend}; EMA alignment insufficient",
    )


def evaluate_rsi(last: pd.Series, *, weight: float) -> ConditionResult:
    rsi = float(last["rsi"])
    if 45 <= rsi <= 68:
        return ConditionResult(
            "RSI",
            "LONG",
            True,
            weight,
            f"RSI bullish momentum zone ({rsi:.1f})",
        )
    if 32 <= rsi <= 55:
        return ConditionResult(
            "RSI",
            "SHORT",
            True,
            weight,
            f"RSI bearish momentum zone ({rsi:.1f})",
        )
    return ConditionResult(
        "RSI",
        "NEUTRAL",
        False,
        weight,
        f"RSI neutral or exhausted ({rsi:.1f})",
    )


def evaluate_volume(last: pd.Series, *, weight: float) -> ConditionResult:
    ratio = float(last.get("volume_ratio", 1.0))
    if pd.isna(ratio):
        return ConditionResult("Volume", "NEUTRAL", False, weight, "Volume data unavailable")

    close = float(last["close"])
    open_ = float(last["open"])

    if ratio >= 1.1:
        if close > open_:
            return ConditionResult(
                "Volume",
                "LONG",
                True,
                weight,
                f"Bullish volume expansion ({ratio:.2f}x average)",
            )
        if close < open_:
            return ConditionResult(
                "Volume",
                "SHORT",
                True,
                weight,
                f"Bearish volume expansion ({ratio:.2f}x average)",
            )
    return ConditionResult(
        "Volume",
        "NEUTRAL",
        False,
        weight,
        f"Volume below confirmation threshold ({ratio:.2f}x)",
    )


def is_volatility_tradeable(last: pd.Series) -> tuple[bool, str]:
    atr_pct = float(last.get("atr_pct", 0.0))
    if pd.isna(atr_pct) or atr_pct <= 0:
        return False, "ATR data unavailable"
    if 0.15 <= atr_pct <= 5.0:
        return True, f"Tradeable volatility ({atr_pct:.2f}% ATR)"
    return False, f"Volatility out of tradeable range ({atr_pct:.2f}% ATR)"


def evaluate_atr(last: pd.Series, *, weight: float) -> ConditionResult:
    ok, reason = is_volatility_tradeable(last)
    if ok:
        return ConditionResult("ATR Volatility", "NEUTRAL", True, weight, reason)
    return ConditionResult("ATR Volatility", "NEUTRAL", False, weight, reason)


def evaluate_all(
    *,
    last: pd.Series,
    trend: str,
    bos: str,
    choch: str,
    liquidity: dict | None,
    order_block: dict | None,
    fvg: dict | None,
    weights: dict[str, float],
) -> list[ConditionResult]:
    price = float(last["close"])
    return [
        evaluate_structure(bos, choch, weight=weights["structure"]),
        evaluate_fvg(fvg, price, weight=weights["fvg"]),
        evaluate_order_block(order_block, price, weight=weights["order_block"]),
        evaluate_liquidity(liquidity, weight=weights["liquidity"]),
        evaluate_ema_trend(trend, last, weight=weights["ema_trend"]),
        evaluate_rsi(last, weight=weights["rsi"]),
        evaluate_volume(last, weight=weights["volume"]),
        evaluate_atr(last, weight=weights["atr"]),
    ]
