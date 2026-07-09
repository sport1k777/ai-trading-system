import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from app.analysis.market_context import MarketContextBuilder
from app.analysis.signal_generator import SignalGenerator
from app.collectors.candles import CandleCollector
from app.config import (
    DEFAULT_CANDLE_LIMIT,
    DEFAULT_INTERVAL,
    DEFAULT_SYMBOL,
    PRO_V2_HTF_INTERVAL,
    SIGNAL_ENGINE_VERSION,
)
from app.risk.risk_manager import RiskManager

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    symbol: str
    df: pd.DataFrame
    signal: dict
    risk: Optional[dict]
    trend: str
    structure: str
    bos: str
    choch: str
    liquidity: Optional[dict]
    order_block: Optional[dict]
    fvg: Optional[dict]
    swing_highs: list
    swing_lows: list

    @property
    def price(self) -> float:
        return float(self.df.iloc[-1]["close"])

    @property
    def atr(self) -> float:
        return float(self.df.iloc[-1]["atr"])


class TradingPipeline:
    """Single entry point for fetching data, running analysis, and computing risk."""

    def __init__(self, collector=None):
        self.collector = collector or CandleCollector()

    def analyze(
        self,
        symbol: str = DEFAULT_SYMBOL,
        interval: str = DEFAULT_INTERVAL,
        limit: int = DEFAULT_CANDLE_LIMIT,
        df: Optional[pd.DataFrame] = None,
    ) -> AnalysisResult:
        if df is None:
            logger.info("Fetching candles for %s", symbol)
            df = self.collector.get_candles(symbol=symbol, interval=interval, limit=limit)

        htf_df = None
        if SIGNAL_ENGINE_VERSION == "v2":
            try:
                htf_df = self.collector.get_candles(
                    symbol=symbol,
                    interval=PRO_V2_HTF_INTERVAL,
                    limit=120,
                )
            except Exception:
                logger.warning("HTF fetch failed for %s; using resampled HTF", symbol)

        ctx = MarketContextBuilder.build(
            df,
            symbol=symbol,
            interval=interval,
            htf_df=htf_df,
        )

        signal = SignalGenerator.generate(
            ctx.df,
            indicators_calculated=True,
            context=ctx,
            symbol=symbol,
            interval=interval,
            htf_df=htf_df,
        )

        swing_highs = signal.get("swing_highs") or ctx.swing_highs
        swing_lows = signal.get("swing_lows") or ctx.swing_lows
        swing_low = swing_lows[-1]["price"] if swing_lows else None
        swing_high = swing_highs[-1]["price"] if swing_highs else None

        risk = RiskManager.calculate(
            ctx.price,
            ctx.atr,
            signal["signal"],
            swing_low=swing_low,
            swing_high=swing_high,
            tp_price=signal.get("tp_price"),
            setup_type=signal.get("setup_type", "pro_signal"),
        )

        if signal.get("entry") and risk is None:
            risk = {
                "entry": signal.get("entry"),
                "stop": signal.get("stop"),
                "tp1": signal.get("tp1", signal.get("tp")),
                "tp2": signal.get("tp2", signal.get("tp")),
                "tp3": signal.get("tp3", signal.get("tp")),
                "rr": signal.get("risk_reward", 0),
            }

        return AnalysisResult(
            symbol=symbol,
            df=ctx.df,
            signal=signal,
            risk=risk,
            trend=ctx.trend,
            structure=ctx.structure,
            bos=ctx.bos,
            choch=ctx.choch,
            liquidity=ctx.liquidity,
            order_block=ctx.order_block,
            fvg=ctx.fvg,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
        )
