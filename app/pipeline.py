"""Market analysis pipeline — generates BUY/SELL/WAIT decisions only.

SIGNAL-ONLY SYSTEM: computes signals and risk levels for alerts.
Never executes trades or interacts with order/position endpoints.
"""
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
from app.risk.signal_levels import normalize_risk_dict

logger = logging.getLogger(__name__)


def _trace(stage: str, **fields) -> None:
    """Temporary production trace — remove after pipeline stall is confirmed fixed."""
    detail = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("TRACE %s%s", stage, f" | {detail}" if detail else "")


def _risk_from_signal(signal: dict) -> Optional[dict]:
    """Use engine-computed levels (includes regime-adjusted risk when present)."""
    if signal.get("signal") not in ("BUY", "SELL"):
        return None
    entry = signal.get("entry")
    stop = signal.get("stop")
    if entry is None or stop is None:
        return None
    tp = signal.get("tp") or signal.get("tp1")
    raw = {
        "entry": entry,
        "stop": stop,
        "tp1": signal.get("tp1", tp),
        "tp2": signal.get("tp2"),
        "tp3": signal.get("tp3"),
        "rr": signal.get("risk_reward", 0),
    }
    return normalize_risk_dict(signal["signal"], raw)


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
        _trace("analyze.start", symbol=symbol, interval=interval, limit=limit)
        if df is None:
            logger.info("Fetching candles for %s", symbol)
            _trace("analyze.fetch_start", symbol=symbol)
            df = self.collector.get_candles(symbol=symbol, interval=interval, limit=limit)
            _trace("analyze.fetch_done", symbol=symbol, rows=len(df))

        htf_df = None
        if SIGNAL_ENGINE_VERSION == "v2":
            try:
                _trace("analyze.htf_fetch_start", symbol=symbol)
                htf_df = self.collector.get_candles(
                    symbol=symbol,
                    interval=PRO_V2_HTF_INTERVAL,
                    limit=120,
                )
                _trace(
                    "analyze.htf_fetch_done",
                    symbol=symbol,
                    rows=len(htf_df) if htf_df is not None else 0,
                )
            except Exception:
                logger.warning("HTF fetch failed for %s; using resampled HTF", symbol)
                _trace("analyze.htf_fetch_failed", symbol=symbol)

        _trace("analyze.context_build_start", symbol=symbol)
        ctx = MarketContextBuilder.build(
            df,
            symbol=symbol,
            interval=interval,
            htf_df=htf_df,
        )
        _trace(
            "analyze.context_build_done",
            symbol=symbol,
            trend=ctx.trend,
            structure=ctx.structure,
            htf_trend=ctx.htf_trend,
        )

        _trace("analyze.engine_start", symbol=symbol, engine=SIGNAL_ENGINE_VERSION)
        signal = SignalGenerator.generate(
            ctx.df,
            indicators_calculated=True,
            context=ctx,
            symbol=symbol,
            interval=interval,
            htf_df=htf_df,
        )
        _trace(
            "analyze.engine_done",
            symbol=symbol,
            signal=signal.get("signal"),
            confidence=signal.get("confidence", signal.get("confluence", 0)),
            grade=signal.get("grade", "n/a"),
        )

        swing_highs = signal.get("swing_highs") or ctx.swing_highs
        swing_lows = signal.get("swing_lows") or ctx.swing_lows
        swing_low = swing_lows[-1]["price"] if swing_lows else None
        swing_high = swing_highs[-1]["price"] if swing_highs else None

        risk = _risk_from_signal(signal)
        if risk is None and signal["signal"] in ("BUY", "SELL"):
            _trace("analyze.risk_calc_start", symbol=symbol, direction=signal["signal"])
            raw_risk = RiskManager.calculate(
                ctx.price,
                ctx.atr,
                signal["signal"],
                swing_low=swing_low,
                swing_high=swing_high,
                tp_price=signal.get("tp_price"),
                setup_type=signal.get("setup_type", "pro_signal"),
            )
            if raw_risk:
                risk = normalize_risk_dict(signal["signal"], raw_risk)
        _trace(
            "analyze.risk_done",
            symbol=symbol,
            has_risk=risk is not None,
            rr=risk.get("rr") if risk else None,
        )

        _trace("analyze.return", symbol=symbol, signal=signal.get("signal"))
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
