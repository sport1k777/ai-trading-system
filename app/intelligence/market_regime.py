"""BTC / global crypto market regime analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from app.analysis.market_context import MarketContext, MarketContextBuilder
from app.collectors.candles import CandleCollector


@dataclass
class GlobalMarketRegime:
    btc_trend: str  # BULLISH, BEARISH, SIDEWAYS
    btc_structure: str
    btc_volatility: str  # HIGH, NORMAL, LOW
    risk_mode: str  # RISK_ON, RISK_OFF, NEUTRAL
    altcoin_long_favorable: bool
    altcoin_short_favorable: bool
    summary: str
    btc_adx: float = 0.0
    btc_atr_pct: float = 0.0

    @property
    def label(self) -> str:
        return f"{self.btc_trend} · {self.risk_mode} · vol {self.btc_volatility}"


class MarketRegimeAnalyzer:
    """Determine global regime before evaluating altcoin setups."""

    def __init__(self, collector: Optional[CandleCollector] = None):
        self.collector = collector or CandleCollector()

    def analyze(self, *, btc_df: Optional[pd.DataFrame] = None) -> GlobalMarketRegime:
        try:
            df = btc_df if btc_df is not None else self.collector.get_candles(
                symbol="BTCUSDT", interval="240", limit=120
            )
        except Exception:
            return GlobalMarketRegime(
                btc_trend="UNKNOWN",
                btc_structure="UNKNOWN",
                btc_volatility="UNKNOWN",
                risk_mode="NEUTRAL",
                altcoin_long_favorable=True,
                altcoin_short_favorable=True,
                summary="BTC data unavailable — neutral regime assumed",
            )

        ctx = MarketContextBuilder.build(df, symbol="BTCUSDT", interval="240", indicators_calculated=False)
        last = ctx.last
        ema20 = float(last.get("ema20", 0))
        ema50 = float(last.get("ema50", 0))
        close = float(last.get("close", 0))
        adx = float(last.get("adx", 0))
        atr = float(last.get("atr", 0))
        atr_pct = (atr / close * 100) if close else 0

        if ema20 > ema50 and close > ema50:
            trend = "BULLISH"
        elif ema20 < ema50 and close < ema50:
            trend = "BEARISH"
        else:
            trend = "SIDEWAYS"

        if atr_pct > 3.0:
            vol = "HIGH"
        elif atr_pct < 0.8:
            vol = "LOW"
        else:
            vol = "NORMAL"

        if trend == "BULLISH" and adx >= 22:
            risk = "RISK_ON"
            long_ok = True
            short_ok = False
        elif trend == "BEARISH" and adx >= 22:
            risk = "RISK_OFF"
            long_ok = False
            short_ok = True
        else:
            risk = "NEUTRAL"
            long_ok = True
            short_ok = True

        return GlobalMarketRegime(
            btc_trend=trend,
            btc_structure=ctx.structure,
            btc_volatility=vol,
            risk_mode=risk,
            altcoin_long_favorable=long_ok,
            altcoin_short_favorable=short_ok,
            summary=f"BTC {trend} ({ctx.structure}), ADX {adx:.0f}, ATR {atr_pct:.2f}%",
            btc_adx=adx,
            btc_atr_pct=atr_pct,
        )

    def compatible_with_direction(self, regime: GlobalMarketRegime, direction: str, *, is_btc: bool = False) -> tuple[bool, str]:
        if is_btc or regime.btc_trend == "UNKNOWN":
            return True, "ok"
        if direction == "BUY" and not regime.altcoin_long_favorable:
            return False, f"BTC regime {regime.risk_mode} contradicts altcoin LONG"
        if direction == "SELL" and not regime.altcoin_short_favorable:
            return False, f"BTC regime {regime.risk_mode} contradicts altcoin SHORT"
        return True, "ok"
