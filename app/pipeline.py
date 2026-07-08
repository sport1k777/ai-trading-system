import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from app.analysis.bos import BOSAnalyzer
from app.analysis.choch import CHOCHAnalyzer
from app.analysis.fvg import FVGAnalyzer
from app.analysis.liquidity import LiquidityAnalyzer
from app.analysis.order_block import OrderBlockAnalyzer
from app.analysis.signal_generator import SignalGenerator
from app.analysis.structure import StructureAnalyzer
from app.analysis.swing import SwingAnalyzer
from app.collectors.candles import CandleCollector
from app.config import DEFAULT_CANDLE_LIMIT, DEFAULT_INTERVAL, DEFAULT_SYMBOL
from app.indicators.signals import SignalIndicators
from app.indicators.trend import TrendAnalyzer
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

        df = SignalIndicators.calculate(df)

        trend = TrendAnalyzer.detect_trend(df)
        structure = StructureAnalyzer.analyze(df)
        bos = BOSAnalyzer.analyze(df)
        choch = CHOCHAnalyzer.analyze(df)
        liquidity = LiquidityAnalyzer.analyze(df)
        order_block = OrderBlockAnalyzer.analyze(df)
        fvg = FVGAnalyzer.analyze(df)
        swing_highs, swing_lows = SwingAnalyzer.analyze(df)

        signal = SignalGenerator.generate(df, indicators_calculated=True)

        swing_highs = signal.get("swing_highs") or []
        swing_lows = signal.get("swing_lows") or []
        swing_low = swing_lows[-1]["price"] if swing_lows else None
        swing_high = swing_highs[-1]["price"] if swing_highs else None

        risk = RiskManager.calculate(
            float(df.iloc[-1]["close"]),
            float(df.iloc[-1]["atr"]),
            signal["signal"],
            swing_low=swing_low,
            swing_high=swing_high,
            tp_price=signal.get("tp_price"),
            setup_type=signal.get("setup_type", "pullback"),
        )

        return AnalysisResult(
            symbol=symbol,
            df=df,
            signal=signal,
            risk=risk,
            trend=trend,
            structure=structure,
            bos=bos,
            choch=choch,
            liquidity=liquidity,
            order_block=order_block,
            fvg=fvg,
            swing_highs=swing_highs,
            swing_lows=swing_lows,
        )
