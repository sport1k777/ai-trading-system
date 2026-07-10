"""Shared market analysis context — single-pass analyzer execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from app.analysis.bos import BOSAnalyzer
from app.analysis.choch import CHOCHAnalyzer
from app.analysis.fvg import FVGAnalyzer
from app.analysis.liquidity import LiquidityAnalyzer
from app.analysis.order_block import OrderBlockAnalyzer
from app.analysis.structure import StructureAnalyzer
from app.analysis.structure_persistence import resolve_htf_trend, resolve_ltf_trend
from app.analysis.swing import SwingAnalyzer
from app.indicators.extended import ExtendedIndicators
from app.indicators.signals import SignalIndicators

logger = logging.getLogger(__name__)

LOOKBACK = 100


@dataclass
class MarketContext:
    """Precomputed analysis bundle shared by pipeline and signal engines."""

    symbol: str
    interval: str
    df: pd.DataFrame
    analysis_df: pd.DataFrame
    htf_df: Optional[pd.DataFrame] = None
    trend: str = "SIDEWAYS"
    structure: str = "RANGE"
    bos: str = "NO_BOS"
    choch: str = "NO_CHOCH"
    liquidity: Optional[dict] = None
    order_block: Optional[dict] = None
    fvg: Optional[dict] = None
    swing_highs: list = field(default_factory=list)
    swing_lows: list = field(default_factory=list)
    htf_trend: str = "SIDEWAYS"
    htf_structure: str = "RANGE"
    htf_bos: str = "NO_BOS"

    @property
    def last(self) -> pd.Series:
        return self.analysis_df.iloc[-1]

    @property
    def price(self) -> float:
        return float(self.last["close"])

    @property
    def atr(self) -> float:
        return float(self.last["atr"])

    @property
    def view(self) -> pd.DataFrame:
        if len(self.analysis_df) > LOOKBACK:
            return self.analysis_df.iloc[-LOOKBACK:]
        return self.analysis_df


class MarketContextBuilder:
    """Build indicators and run structure analyzers once per scan."""

    REQUIRED = (
        "ema20", "ema50", "ema200", "rsi", "macd_diff", "atr", "adx",
        "bb_upper", "bb_mid", "bb_lower",
    )

    @staticmethod
    def _closed_bars(df: pd.DataFrame) -> pd.DataFrame:
        """Exclude the forming candle to reduce repaint risk."""
        if len(df) < 3:
            return df
        return df.iloc[:-1].copy()

    @staticmethod
    def resample_htf(ltf_df: pd.DataFrame, bars_per_htf: int = 4) -> pd.DataFrame:
        """Resample LTF OHLCV into HTF bars using only complete periods."""
        if len(ltf_df) < bars_per_htf * 10:
            return pd.DataFrame()

        n = (len(ltf_df) // bars_per_htf) * bars_per_htf
        subset = ltf_df.iloc[:n]
        rows = []
        for i in range(0, n, bars_per_htf):
            chunk = subset.iloc[i : i + bars_per_htf]
            rows.append(
                {
                    "timestamp": chunk.iloc[-1]["timestamp"] if "timestamp" in chunk.columns else i,
                    "open": float(chunk.iloc[0]["open"]),
                    "high": float(chunk["high"].max()),
                    "low": float(chunk["low"].min()),
                    "close": float(chunk.iloc[-1]["close"]),
                    "volume": float(chunk["volume"].sum()),
                }
            )
        return pd.DataFrame(rows)

    @classmethod
    def build(
        cls,
        df: pd.DataFrame,
        *,
        symbol: str = "BTCUSDT",
        interval: str = "15",
        htf_df: Optional[pd.DataFrame] = None,
        indicators_calculated: bool = False,
        use_extended: bool = True,
        bars_per_htf: int = 4,
    ) -> MarketContext:
        if not indicators_calculated:
            df = SignalIndicators.calculate(df)
        if use_extended:
            df = ExtendedIndicators.calculate(df)

        analysis_df = cls._closed_bars(df)
        view = analysis_df.iloc[-LOOKBACK:] if len(analysis_df) > LOOKBACK else analysis_df

        if htf_df is not None and len(htf_df) >= 30:
            htf_closed = cls._closed_bars(htf_df)
            htf_view = SignalIndicators.calculate(htf_closed)
        else:
            raw_htf = cls.resample_htf(analysis_df, bars_per_htf=bars_per_htf)
            htf_view = SignalIndicators.calculate(raw_htf) if len(raw_htf) >= 30 else pd.DataFrame()

        structure = StructureAnalyzer.analyze(view)
        ctx = MarketContext(
            symbol=symbol,
            interval=interval,
            df=df,
            analysis_df=analysis_df,
            htf_df=htf_view if len(htf_view) >= 30 else None,
            trend=resolve_ltf_trend(view, structure),
            structure=structure,
            bos=BOSAnalyzer.analyze(view),
            choch=CHOCHAnalyzer.analyze(view),
            liquidity=LiquidityAnalyzer.analyze(view),
            order_block=OrderBlockAnalyzer.analyze(view),
            fvg=FVGAnalyzer.analyze(view),
            swing_highs=SwingAnalyzer.analyze(view, lookback=50)[0],
            swing_lows=SwingAnalyzer.analyze(view, lookback=50)[1],
        )

        if ctx.htf_df is not None and len(ctx.htf_df) >= 30:
            htf_view_df = ctx.htf_df.iloc[-60:] if len(ctx.htf_df) > 60 else ctx.htf_df
            ctx.htf_trend = resolve_htf_trend(htf_view_df)
            ctx.htf_structure = StructureAnalyzer.analyze(htf_view_df)
            ctx.htf_bos = BOSAnalyzer.analyze(htf_view_df)

        logger.debug(
            "%s context: trend=%s structure=%s htf=%s",
            symbol, ctx.trend, ctx.structure, ctx.htf_trend,
        )
        return ctx

    @staticmethod
    def is_ready(ctx: MarketContext) -> bool:
        last = ctx.last
        return all(pd.notna(last.get(c)) for c in MarketContextBuilder.REQUIRED)
