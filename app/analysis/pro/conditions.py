from __future__ import annotations

import pandas as pd

from app.analysis.poi_proximity import near_bearish_poi, near_bullish_poi
from app.analysis.pro.models import ConditionResult


def evaluate_bos(bos: str, *, weight: float) -> ConditionResult:
    if bos == "BULLISH_BOS":
        return ConditionResult("BOS", "LONG", True, weight, "Bullish BOS confirmed")
    if bos == "BEARISH_BOS":
        return ConditionResult("BOS", "SHORT", True, weight, "Bearish BOS confirmed")
    return ConditionResult("BOS", "NEUTRAL", False, weight, "No active BOS")


def evaluate_choch(choch: str, *, weight: float) -> ConditionResult:
    if choch == "BULLISH_CHOCH":
        return ConditionResult("CHOCH", "LONG", True, weight, "Bullish CHOCH confirmed")
    if choch == "BEARISH_CHOCH":
        return ConditionResult("CHOCH", "SHORT", True, weight, "Bearish CHOCH confirmed")
    return ConditionResult("CHOCH", "NEUTRAL", False, weight, "No active CHOCH")


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


def evaluate_fvg(
    fvg: dict | None,
    price: float,
    *,
    weight: float,
    poi_tolerance_pct: float | None = None,
) -> ConditionResult:
    if not fvg:
        return ConditionResult("Fair Value Gap", "NEUTRAL", False, weight, "No active FVG")

    top, bottom = float(fvg["top"]), float(fvg["bottom"])
    tol = poi_tolerance_pct
    if fvg["type"] == "BULLISH" and near_bullish_poi(price, bottom, top, pct=tol):
        return ConditionResult(
            "Fair Value Gap",
            "LONG",
            True,
            weight,
            f"Price within 0.3% of bullish FVG ({bottom:.2f}–{top:.2f})",
        )
    if fvg["type"] == "BEARISH" and near_bearish_poi(price, bottom, top, pct=tol):
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
    poi_tolerance_pct: float | None = None,
) -> ConditionResult:
    if not order_block:
        return ConditionResult("Order Block", "NEUTRAL", False, weight, "No active order block")

    tol = poi_tolerance_pct
    bullish = order_block.get("bullish")
    if bullish and near_bullish_poi(price, bullish["low"], bullish["high"], pct=tol):
        return ConditionResult(
            "Order Block",
            "LONG",
            True,
            weight,
            f"Price within 0.3% of bullish OB ({bullish['low']:.2f}–{bullish['high']:.2f})",
        )

    bearish = order_block.get("bearish")
    if bearish and near_bearish_poi(price, bearish["low"], bearish["high"], pct=tol):
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


def evaluate_adx(last: pd.Series, trend: str, *, weight: float) -> ConditionResult:
    from app.config import MIN_ADX

    adx = float(last.get("adx", 0))
    if pd.isna(adx):
        return ConditionResult("ADX Trend", "NEUTRAL", False, weight, "ADX unavailable")
    if adx >= MIN_ADX:
        if trend == "BULLISH":
            direction: str = "LONG"
        elif trend == "BEARISH":
            direction = "SHORT"
        else:
            direction = "NEUTRAL"
        return ConditionResult(
            "ADX Trend",
            direction,
            True,
            weight,
            f"ADX {adx:.1f} confirms trend strength (min {MIN_ADX:.0f})",
        )
    return ConditionResult(
        "ADX Trend",
        "NEUTRAL",
        False,
        weight,
        f"ADX {adx:.1f} below threshold {MIN_ADX:.0f}",
    )


def evaluate_htf_alignment(htf_trend: str, ltf_trend: str, *, weight: float) -> ConditionResult:
    if htf_trend == "BULLISH":
        return ConditionResult("HTF Alignment", "LONG", True, weight, "HTF bullish alignment")
    if htf_trend == "BEARISH":
        return ConditionResult("HTF Alignment", "SHORT", True, weight, "HTF bearish alignment")
    if ltf_trend == "BULLISH":
        return ConditionResult("HTF Alignment", "LONG", True, weight, "LTF bullish (HTF neutral)")
    if ltf_trend == "BEARISH":
        return ConditionResult("HTF Alignment", "SHORT", True, weight, "LTF bearish (HTF neutral)")
    return ConditionResult("HTF Alignment", "NEUTRAL", False, weight, "No HTF/LTF alignment")


def is_volatility_tradeable(last: pd.Series, *, atr_min: float = 0.15, atr_max: float = 5.0) -> tuple[bool, str]:
    atr_pct = float(last.get("atr_pct", 0.0))
    if pd.isna(atr_pct) or atr_pct <= 0:
        return False, "ATR data unavailable"
    if atr_min <= atr_pct <= atr_max:
        return True, f"Tradeable volatility ({atr_pct:.2f}% ATR)"
    return False, f"Volatility out of tradeable range ({atr_pct:.2f}% ATR)"


def evaluate_atr(
    last: pd.Series,
    *,
    weight: float,
    atr_min: float = 0.15,
    atr_max: float = 5.0,
) -> ConditionResult:
    ok, reason = is_volatility_tradeable(last, atr_min=atr_min, atr_max=atr_max)
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
    htf_trend: str = "SIDEWAYS",
    poi_tolerance_pct: float | None = None,
    atr_min: float = 0.15,
    atr_max: float = 5.0,
    include_structure_detail: bool = True,
) -> list[ConditionResult]:
    price = float(last["close"])
    structure_weight = weights["structure"]
    bos_weight = structure_weight * 0.55
    choch_weight = structure_weight * 0.45

    conditions: list[ConditionResult] = []
    if include_structure_detail:
        conditions.extend([
            evaluate_bos(bos, weight=bos_weight),
            evaluate_choch(choch, weight=choch_weight),
        ])
    else:
        conditions.append(evaluate_structure(bos, choch, weight=structure_weight))

    conditions.extend([
        evaluate_fvg(fvg, price, weight=weights["fvg"], poi_tolerance_pct=poi_tolerance_pct),
        evaluate_order_block(
            order_block, price, weight=weights["order_block"], poi_tolerance_pct=poi_tolerance_pct
        ),
        evaluate_liquidity(liquidity, weight=weights["liquidity"]),
        evaluate_ema_trend(trend, last, weight=weights["ema_trend"]),
        evaluate_adx(last, trend, weight=weights.get("adx", weights["ema_trend"] * 0.8)),
        evaluate_htf_alignment(htf_trend, trend, weight=weights.get("htf", weights["ema_trend"])),
        evaluate_rsi(last, weight=weights["rsi"]),
        evaluate_volume(last, weight=weights["volume"]),
        evaluate_atr(last, weight=weights["atr"], atr_min=atr_min, atr_max=atr_max),
    ])
    return conditions
