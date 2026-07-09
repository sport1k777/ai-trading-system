"""
Signal generator — routes to PRO v1 or PRO v2 based on SIGNAL_ENGINE_VERSION.
Preserves backward-compatible generate() interface.
"""

from __future__ import annotations

from typing import Optional

from app.analysis.market_context import MarketContext
from app.analysis.pro.engine import SignalEnginePro
from app.analysis.pro_v2.engine import SignalEngineProV2
from app.config import SIGNAL_ENGINE_VERSION


class SignalGenerator:
    """Facade for live and backtest signal generation."""

    REQUIRED = SignalEngineProV2.REQUIRED if SIGNAL_ENGINE_VERSION == "v2" else SignalEnginePro.REQUIRED

    @staticmethod
    def generate(
        df,
        *,
        indicators_calculated: bool = False,
        context: Optional[MarketContext] = None,
        symbol: str = "BTCUSDT",
        interval: str = "15",
        htf_df=None,
    ):
        if SIGNAL_ENGINE_VERSION == "v2":
            return SignalEngineProV2.generate(
                df,
                indicators_calculated=indicators_calculated,
                context=context,
                symbol=symbol,
                interval=interval,
                htf_df=htf_df,
            )
        return SignalEnginePro.generate(
            df,
            indicators_calculated=indicators_calculated,
            context=context,
        )

    @staticmethod
    def engine_version() -> str:
        return SIGNAL_ENGINE_VERSION
