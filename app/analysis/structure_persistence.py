"""Persistent market structure detection without repainting or look-ahead bias.

All scans use only closed bars. Historical events at bar *i* are evaluated on
``df.iloc[: i + 1]`` so future candles never influence past structure labels.
"""

from __future__ import annotations

import pandas as pd

from app.analysis.structure import StructureAnalyzer
from app.analysis.swing import SwingAnalyzer
from app.config import (
    STRUCTURE_BOS_LOOKBACK,
    STRUCTURE_CHOCH_LOOKBACK,
    STRUCTURE_HTF_LOOKBACK,
)
from app.indicators.trend import TrendAnalyzer

MIN_BOS_BARS = 25


def _slice_closed(df: pd.DataFrame, end_index: int) -> pd.DataFrame:
    return df.iloc[: end_index + 1]


def _bos_at_bar(df: pd.DataFrame) -> str | None:
    """Detect BOS on the last bar of *df* (already truncated to closed history)."""
    if len(df) < MIN_BOS_BARS:
        return None

    highs, lows = SwingAnalyzer.analyze(df, window=3)
    close = float(df["close"].iloc[-1])

    bull = False
    bear = False
    if highs:
        if close > highs[-1]["price"]:
            bull = True
    if lows:
        if close < lows[-1]["price"]:
            bear = True

    if bull and not bear:
        return "BULLISH_BOS"
    if bear and not bull:
        return "BEARISH_BOS"
    if bull and bear:
        return "BULLISH_BOS" if close >= float(df["open"].iloc[-1]) else "BEARISH_BOS"
    return None


def _choch_at_bar(df: pd.DataFrame) -> str | None:
    if len(df) < MIN_BOS_BARS:
        return None

    highs, lows = SwingAnalyzer.analyze(df)
    if len(highs) < 2 or len(lows) < 2:
        return None

    prev_high = highs[-2]["price"]
    last_high = highs[-1]["price"]
    prev_low = lows[-2]["price"]
    last_low = lows[-1]["price"]
    last_close = float(df["close"].iloc[-1])

    if last_high > prev_high and last_low > prev_low and last_close > prev_high:
        return "BULLISH_CHOCH"
    if last_high < prev_high and last_low < prev_low and last_close < prev_low:
        return "BEARISH_CHOCH"
    return None


def _recent_event_indices(
    df: pd.DataFrame,
    *,
    lookback: int,
    detector,
) -> tuple[int | None, int | None]:
    """Return (last_bull_bar_index, last_bear_bar_index) within lookback."""
    if len(df) < MIN_BOS_BARS:
        return None, None

    start = max(MIN_BOS_BARS - 1, len(df) - lookback)
    last_bull: int | None = None
    last_bear: int | None = None

    for i in range(start, len(df)):
        event = detector(_slice_closed(df, i))
        if event in ("BULLISH_BOS", "BULLISH_CHOCH"):
            last_bull = i
        elif event in ("BEARISH_BOS", "BEARISH_CHOCH"):
            last_bear = i

    return last_bull, last_bear


def _resolve_directional_event(
    df: pd.DataFrame,
    *,
    lookback: int,
    detector,
    neutral: str,
    bull_label: str,
    bear_label: str,
) -> str:
    last_bull, last_bear = _recent_event_indices(df, lookback=lookback, detector=detector)

    if last_bull is None and last_bear is None:
        return neutral
    if last_bull is not None and last_bear is None:
        return bull_label
    if last_bear is not None and last_bull is None:
        return bear_label
    assert last_bull is not None and last_bear is not None
    return bull_label if last_bull > last_bear else bear_label


def analyze_bos_persistent(
    df: pd.DataFrame,
    *,
    lookback: int | None = None,
) -> str:
    window = lookback if lookback is not None else STRUCTURE_BOS_LOOKBACK
    return _resolve_directional_event(
        df,
        lookback=window,
        detector=_bos_at_bar,
        neutral="NO_BOS",
        bull_label="BULLISH_BOS",
        bear_label="BEARISH_BOS",
    )


def analyze_choch_persistent(
    df: pd.DataFrame,
    *,
    lookback: int | None = None,
) -> str:
    window = lookback if lookback is not None else STRUCTURE_CHOCH_LOOKBACK
    return _resolve_directional_event(
        df,
        lookback=window,
        detector=_choch_at_bar,
        neutral="NO_CHOCH",
        bull_label="BULLISH_CHOCH",
        bear_label="BEARISH_CHOCH",
    )


def _htf_bias_at_bar(df: pd.DataFrame) -> str | None:
    if len(df) < 30:
        return None
    view = df.iloc[-60:] if len(df) > 60 else df
    trend = TrendAnalyzer.detect_trend(view)
    structure = StructureAnalyzer.analyze(view)

    if trend == "BULLISH" or structure == "UPTREND":
        return "BULLISH"
    if trend == "BEARISH" or structure == "DOWNTREND":
        return "BEARISH"
    return None


def _htf_invalidates_bull(df: pd.DataFrame) -> bool:
    _, lows = SwingAnalyzer.analyze(df.iloc[-40:] if len(df) > 40 else df, window=3)
    if not lows:
        return False
    return float(df["close"].iloc[-1]) < lows[-1]["price"]


def _htf_invalidates_bear(df: pd.DataFrame) -> bool:
    highs, _ = SwingAnalyzer.analyze(df.iloc[-40:] if len(df) > 40 else df, window=3)
    if not highs:
        return False
    return float(df["close"].iloc[-1]) > highs[-1]["price"]


def resolve_htf_trend(
    htf_df: pd.DataFrame,
    *,
    lookback: int | None = None,
) -> str:
    """Persist HTF directional bias until structure clearly invalidates it."""
    if len(htf_df) < 30:
        return "SIDEWAYS"

    window = lookback if lookback is not None else STRUCTURE_HTF_LOOKBACK
    start = max(29, len(htf_df) - window)
    last_bull: int | None = None
    last_bear: int | None = None

    for i in range(start, len(htf_df)):
        bias = _htf_bias_at_bar(_slice_closed(htf_df, i))
        if bias == "BULLISH":
            last_bull = i
        elif bias == "BEARISH":
            last_bear = i

    if last_bull is None and last_bear is None:
        structure = StructureAnalyzer.analyze(htf_df)
        if structure == "UPTREND":
            return "BULLISH"
        if structure == "DOWNTREND":
            return "BEARISH"
        return "SIDEWAYS"

    if last_bull is not None and (last_bear is None or last_bull > last_bear):
        if _htf_invalidates_bull(htf_df):
            if last_bear is not None and last_bear > last_bull:
                return "BEARISH"
            return "SIDEWAYS"
        return "BULLISH"

    if last_bear is not None and (last_bull is None or last_bear > last_bull):
        if _htf_invalidates_bear(htf_df):
            if last_bull is not None and last_bull > last_bear:
                return "BULLISH"
            return "SIDEWAYS"
        return "BEARISH"

    return "SIDEWAYS"


def resolve_ltf_trend(df: pd.DataFrame, structure: str) -> str:
    """Combine EMA trend with structure; structure fills SIDEWAYS gaps."""
    ema_trend = TrendAnalyzer.detect_trend(df)
    if ema_trend in ("BULLISH", "BEARISH"):
        return ema_trend
    if structure == "UPTREND":
        return "BULLISH"
    if structure == "DOWNTREND":
        return "BEARISH"
    return "SIDEWAYS"
