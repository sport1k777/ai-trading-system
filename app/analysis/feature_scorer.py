"""
Individual feature scoring for the AI Signal Engine.
Each feature returns buy_score, sell_score (0-100) and a reason string.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from app.analysis.bos import BOSAnalyzer
from app.analysis.choch import CHOCHAnalyzer
from app.analysis.fvg import FVGAnalyzer
from app.analysis.liquidity import LiquidityAnalyzer
from app.analysis.order_block import OrderBlockAnalyzer
from app.analysis.structure import StructureAnalyzer
from app.analysis.swing import SwingAnalyzer
from app.indicators.trend import TrendAnalyzer


@dataclass
class FeatureScore:
    name: str
    buy_score: float
    sell_score: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "buy_score": round(self.buy_score, 1),
            "sell_score": round(self.sell_score, 1),
            "reason": self.reason,
        }


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


class FeatureScorer:
    """Score 20 market features individually for bullish/bearish bias."""

    @staticmethod
    def score_all(
        df: pd.DataFrame,
        *,
        liquidity=None,
        order_block=None,
        fvg=None,
        structure: Optional[str] = None,
        bos: Optional[str] = None,
        choch: Optional[str] = None,
        swing_highs=None,
        swing_lows=None,
    ) -> list[FeatureScore]:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = float(last["close"])
        scores: list[FeatureScore] = []

        scores.append(FeatureScorer._score_ema(last, price))
        scores.append(FeatureScorer._score_rsi(last, prev))
        scores.append(FeatureScorer._score_macd(last, prev))
        scores.append(FeatureScorer._score_adx(last))
        scores.append(FeatureScorer._score_atr(last, df))
        scores.append(FeatureScorer._score_vwap(last, price))
        scores.append(FeatureScorer._score_bollinger(last, price))
        scores.append(FeatureScorer._score_volume(last))
        scores.append(FeatureScorer._score_volume_profile(last, price))
        scores.append(FeatureScorer._score_market_structure(structure or StructureAnalyzer.analyze(df)))
        scores.append(FeatureScorer._score_liquidity_sweeps(liquidity or LiquidityAnalyzer.analyze(df)))
        scores.append(FeatureScorer._score_order_blocks(order_block or OrderBlockAnalyzer.analyze(df), price))
        scores.append(FeatureScorer._score_fvg(fvg or FVGAnalyzer.analyze(df), price))
        scores.append(FeatureScorer._score_support_resistance(swing_highs, swing_lows, price))
        scores.append(FeatureScorer._score_trend_strength(df))
        scores.append(FeatureScorer._score_mtf(df))
        scores.append(FeatureScorer._score_volatility(last))
        scores.append(FeatureScorer._score_momentum(last))
        scores.append(FeatureScorer._score_session(last))
        scores.append(FeatureScorer._score_candle_structure(last, prev))
        scores.append(FeatureScorer._score_bos(bos or BOSAnalyzer.analyze(df)))
        scores.append(FeatureScorer._score_choch(choch or CHOCHAnalyzer.analyze(df)))

        return scores

    @staticmethod
    def _score_ema(last, price) -> FeatureScore:
        e20, e50, e200 = float(last["ema20"]), float(last["ema50"]), float(last["ema200"])
        buy = 50.0
        sell = 50.0
        if price > e20 > e50 > e200:
            buy, sell = 95, 15
            reason = "Full EMA stack bullish"
        elif price < e20 < e50 < e200:
            buy, sell = 15, 95
            reason = "Full EMA stack bearish"
        elif price > e50 and e20 > e50:
            buy, sell = 75, 35
            reason = "Price above EMA50, EMA20>EMA50"
        elif price < e50 and e20 < e50:
            buy, sell = 35, 75
            reason = "Price below EMA50, EMA20<EMA50"
        else:
            reason = "Mixed EMA alignment"
        return FeatureScore("EMA", buy, sell, reason)

    @staticmethod
    def _score_rsi(last, prev) -> FeatureScore:
        rsi = float(last["rsi"])
        prev_rsi = float(prev["rsi"])
        rising = rsi > prev_rsi
        if rsi < 30:
            buy, sell = 90, 10
            reason = f"RSI oversold ({rsi:.0f})"
        elif rsi > 70:
            buy, sell = 10, 90
            reason = f"RSI overbought ({rsi:.0f})"
        elif 40 <= rsi <= 55 and rising:
            buy, sell = 80, 30
            reason = f"RSI bullish zone ({rsi:.0f}) rising"
        elif 45 <= rsi <= 60 and not rising:
            buy, sell = 30, 80
            reason = f"RSI bearish zone ({rsi:.0f}) falling"
        elif rsi > 50:
            buy, sell = 65, 40
            reason = f"RSI above midline ({rsi:.0f})"
        else:
            buy, sell = 40, 65
            reason = f"RSI below midline ({rsi:.0f})"
        return FeatureScore("RSI", buy, sell, reason)

    @staticmethod
    def _score_macd(last, prev) -> FeatureScore:
        macd = float(last["macd_diff"])
        prev_macd = float(last["macd_diff_prev"])
        if macd > 0 and macd > prev_macd:
            buy, sell = 85, 20
            reason = "MACD bullish and accelerating"
        elif macd < 0 and macd < prev_macd:
            buy, sell = 20, 85
            reason = "MACD bearish and accelerating"
        elif macd > prev_macd:
            buy, sell = 70, 40
            reason = "MACD turning up"
        elif macd < prev_macd:
            buy, sell = 40, 70
            reason = "MACD turning down"
        else:
            buy, sell = 50, 50
            reason = "MACD neutral"
        return FeatureScore("MACD", buy, sell, reason)

    @staticmethod
    def _score_adx(last) -> FeatureScore:
        adx = float(last["adx"])
        if adx >= 40:
            buy, sell = 70, 70
            reason = f"Strong trend ADX={adx:.0f}"
        elif adx >= 25:
            buy, sell = 60, 60
            reason = f"Moderate trend ADX={adx:.0f}"
        else:
            buy, sell = 45, 45
            reason = f"Ranging market ADX={adx:.0f}"
        return FeatureScore("ADX", buy, sell, reason)

    @staticmethod
    def _score_atr(last, df) -> FeatureScore:
        atr_pct = float(last.get("atr_pct", 0))
        recent = df["atr_pct"].tail(20).mean()
        if pd.isna(recent):
            return FeatureScore("ATR", 50, 50, "ATR data unavailable")
        if atr_pct > recent * 1.3:
            buy, sell = 55, 55
            reason = f"Expanded volatility ATR%={atr_pct:.2f}"
        elif atr_pct < recent * 0.7:
            buy, sell = 40, 40
            reason = f"Contracted volatility ATR%={atr_pct:.2f}"
        else:
            buy, sell = 55, 55
            reason = f"Normal volatility ATR%={atr_pct:.2f}"
        return FeatureScore("ATR", buy, sell, reason)

    @staticmethod
    def _score_vwap(last, price) -> FeatureScore:
        vwap = last.get("vwap")
        if pd.isna(vwap):
            return FeatureScore("VWAP", 50, 50, "VWAP unavailable")
        vwap = float(vwap)
        dist = (price - vwap) / vwap * 100
        if dist > 0.3:
            buy, sell = 80, 25
            reason = f"Price above VWAP (+{dist:.2f}%)"
        elif dist < -0.3:
            buy, sell = 25, 80
            reason = f"Price below VWAP ({dist:.2f}%)"
        else:
            buy, sell = 50, 50
            reason = "Price at VWAP"
        return FeatureScore("VWAP", buy, sell, reason)

    @staticmethod
    def _score_bollinger(last, price) -> FeatureScore:
        bb_u, bb_m, bb_l = float(last["bb_upper"]), float(last["bb_mid"]), float(last["bb_lower"])
        width = bb_u - bb_l
        if width <= 0:
            return FeatureScore("Bollinger Bands", 50, 50, "BB unavailable")
        pos = (price - bb_l) / width
        if pos <= 0.1:
            buy, sell = 90, 15
            reason = "Price at lower Bollinger Band"
        elif pos >= 0.9:
            buy, sell = 15, 90
            reason = "Price at upper Bollinger Band"
        elif price > bb_m:
            buy, sell = 65, 40
            reason = "Price above BB midline"
        else:
            buy, sell = 40, 65
            reason = "Price below BB midline"
        return FeatureScore("Bollinger Bands", buy, sell, reason)

    @staticmethod
    def _score_volume(last) -> FeatureScore:
        vr = float(last.get("volume_ratio", 1.0))
        if pd.isna(vr):
            vr = 1.0
        if vr >= 2.0:
            buy, sell = 75, 75
            reason = f"High volume spike ({vr:.1f}x avg)"
        elif vr >= 1.3:
            buy, sell = 65, 65
            reason = f"Above average volume ({vr:.1f}x)"
        elif vr <= 0.6:
            buy, sell = 35, 35
            reason = f"Low volume ({vr:.1f}x avg)"
        else:
            buy, sell = 50, 50
            reason = f"Normal volume ({vr:.1f}x avg)"
        return FeatureScore("Volume", buy, sell, reason)

    @staticmethod
    def _score_volume_profile(last, price) -> FeatureScore:
        poc = last.get("poc")
        vah = last.get("vah")
        val = last.get("val")
        if pd.isna(poc):
            return FeatureScore("Volume Profile", 50, 50, "Volume profile unavailable")
        poc, vah, val = float(poc), float(vah), float(val)
        if price > vah:
            buy, sell = 75, 30
            reason = "Price above value area high"
        elif price < val:
            buy, sell = 30, 75
            reason = "Price below value area low"
        elif price > poc:
            buy, sell = 65, 40
            reason = "Price above POC"
        elif price < poc:
            buy, sell = 40, 65
            reason = "Price below POC"
        else:
            buy, sell = 50, 50
            reason = "Price at POC"
        return FeatureScore("Volume Profile", buy, sell, reason)

    @staticmethod
    def _score_market_structure(structure: str) -> FeatureScore:
        if structure == "UPTREND":
            buy, sell = 90, 15
            reason = "Market structure uptrend (HH/HL)"
        elif structure == "DOWNTREND":
            buy, sell = 15, 90
            reason = "Market structure downtrend (LH/LL)"
        else:
            buy, sell = 45, 45
            reason = "Market structure ranging"
        return FeatureScore("Market Structure", buy, sell, reason)

    @staticmethod
    def _score_liquidity_sweeps(liquidity) -> FeatureScore:
        if not liquidity:
            return FeatureScore("Liquidity Sweeps", 50, 50, "No liquidity sweep")
        if liquidity["type"] == "SELL_SIDE_SWEEP":
            buy, sell = 85, 20
            reason = "Sell-side liquidity swept (bullish reversal)"
        else:
            buy, sell = 20, 85
            reason = "Buy-side liquidity swept (bearish reversal)"
        return FeatureScore("Liquidity Sweeps", buy, sell, reason)

    @staticmethod
    def _score_order_blocks(ob, price) -> FeatureScore:
        if not ob:
            return FeatureScore("Order Blocks", 50, 50, "No active order block")
        bull = ob.get("bullish")
        bear = ob.get("bearish")
        buy, sell = 50.0, 50.0
        reasons = []
        if bull and bull["low"] <= price <= bull["high"] * 1.005:
            buy = 85
            reasons.append("Price in bullish OB zone")
        if bear and bear["low"] * 0.995 <= price <= bear["high"]:
            sell = 85
            reasons.append("Price in bearish OB zone")
        reason = "; ".join(reasons) if reasons else "No OB proximity"
        return FeatureScore("Order Blocks", buy, sell, reason)

    @staticmethod
    def _score_fvg(fvg, price) -> FeatureScore:
        if not fvg:
            return FeatureScore("Fair Value Gaps", 50, 50, "No active FVG")
        if fvg["type"] == "BULLISH" and fvg["bottom"] <= price <= fvg["top"]:
            buy, sell = 85, 20
            reason = "Price in bullish FVG"
        elif fvg["type"] == "BEARISH" and fvg["bottom"] <= price <= fvg["top"]:
            buy, sell = 20, 85
            reason = "Price in bearish FVG"
        elif fvg["type"] == "BULLISH":
            buy, sell = 70, 35
            reason = "Active bullish FVG below"
        else:
            buy, sell = 35, 70
            reason = "Active bearish FVG above"
        return FeatureScore("Fair Value Gaps", buy, sell, reason)

    @staticmethod
    def _score_support_resistance(swing_highs, swing_lows, price) -> FeatureScore:
        buy, sell = 50.0, 50.0
        reason = "No S/R proximity"
        if swing_lows:
            support = swing_lows[-1]["price"]
            dist = abs(price - support) / price * 100
            if dist < 0.5:
                buy = 85
                reason = f"At support ({support:.2f})"
        if swing_highs:
            resistance = swing_highs[-1]["price"]
            dist = abs(price - resistance) / price * 100
            if dist < 0.5:
                sell = 85
                reason = f"At resistance ({resistance:.2f})"
        return FeatureScore("Support/Resistance", buy, sell, reason)

    @staticmethod
    def _score_trend_strength(df) -> FeatureScore:
        trend = TrendAnalyzer.detect_trend(df)
        adx = float(df.iloc[-1]["adx"])
        if trend == "BULLISH" and adx >= 25:
            buy, sell = 85, 20
            reason = f"Strong bullish trend ADX={adx:.0f}"
        elif trend == "BEARISH" and adx >= 25:
            buy, sell = 20, 85
            reason = f"Strong bearish trend ADX={adx:.0f}"
        elif trend == "BULLISH":
            buy, sell = 70, 35
            reason = "Bullish trend (weak ADX)"
        elif trend == "BEARISH":
            buy, sell = 35, 70
            reason = "Bearish trend (weak ADX)"
        else:
            buy, sell = 45, 45
            reason = "Sideways trend"
        return FeatureScore("Trend Strength", buy, sell, reason)

    @staticmethod
    def _score_mtf(df) -> FeatureScore:
        """Higher timeframe proxy: resample every 4 bars."""
        if len(df) < 80:
            return FeatureScore("Multi-Timeframe", 50, 50, "Insufficient data for MTF")
        htf = df.iloc[::4].copy()
        if len(htf) < 30:
            return FeatureScore("Multi-Timeframe", 50, 50, "Insufficient HTF bars")
        htf_trend = TrendAnalyzer.detect_trend(htf)
        htf_struct = StructureAnalyzer.analyze(htf)
        if htf_trend == "BULLISH" and htf_struct == "UPTREND":
            buy, sell = 90, 15
            reason = "HTF bullish trend confirmed"
        elif htf_trend == "BEARISH" and htf_struct == "DOWNTREND":
            buy, sell = 15, 90
            reason = "HTF bearish trend confirmed"
        elif htf_trend == "BULLISH":
            buy, sell = 70, 35
            reason = "HTF bullish bias"
        elif htf_trend == "BEARISH":
            buy, sell = 35, 70
            reason = "HTF bearish bias"
        else:
            buy, sell = 45, 45
            reason = "HTF ranging"
        return FeatureScore("Multi-Timeframe", buy, sell, reason)

    @staticmethod
    def _score_volatility(last) -> FeatureScore:
        regime = float(last.get("vol_regime", 1.0))
        bb_width = float(last.get("bb_width", 0))
        if pd.isna(regime):
            regime = 1.0
        if regime > 1.3:
            buy, sell = 55, 55
            reason = f"Expanding volatility (regime={regime:.2f})"
        elif regime < 0.7:
            buy, sell = 40, 40
            reason = f"Contracting volatility (regime={regime:.2f})"
        else:
            buy, sell = 55, 55
            reason = f"Normal volatility BB width={bb_width:.1f}%"
        return FeatureScore("Volatility", buy, sell, reason)

    @staticmethod
    def _score_momentum(last) -> FeatureScore:
        mom = float(last.get("momentum_score", 0))
        if pd.isna(mom):
            return FeatureScore("Momentum", 50, 50, "Momentum unavailable")
        if mom > 2:
            buy, sell = 85, 20
            reason = f"Strong positive momentum ({mom:.1f}%)"
        elif mom < -2:
            buy, sell = 20, 85
            reason = f"Strong negative momentum ({mom:.1f}%)"
        elif mom > 0.5:
            buy, sell = 70, 40
            reason = f"Positive momentum ({mom:.1f}%)"
        elif mom < -0.5:
            buy, sell = 40, 70
            reason = f"Negative momentum ({mom:.1f}%)"
        else:
            buy, sell = 50, 50
            reason = "Flat momentum"
        return FeatureScore("Momentum", buy, sell, reason)

    @staticmethod
    def _score_session(last) -> FeatureScore:
        ts = last.get("timestamp")
        if ts is None or pd.isna(ts):
            return FeatureScore("Session Strength", 50, 50, "Session unknown")
        hour = pd.Timestamp(ts).hour
        # London/NY overlap (13-16 UTC) = highest activity
        if 13 <= hour < 16:
            buy, sell = 70, 70
            reason = "London/NY overlap (high activity)"
        elif 8 <= hour < 13:
            buy, sell = 60, 60
            reason = "London session"
        elif 16 <= hour < 21:
            buy, sell = 60, 60
            reason = "NY session"
        else:
            buy, sell = 40, 40
            reason = "Asia/off-hours (lower activity)"
        return FeatureScore("Session Strength", buy, sell, reason)

    @staticmethod
    def _score_candle_structure(last, prev) -> FeatureScore:
        o, h, l, c = float(last["open"]), float(last["high"]), float(last["low"]), float(last["close"])
        po, ph, pl, pc = float(prev["open"]), float(prev["high"]), float(prev["low"]), float(prev["close"])
        body = abs(c - o)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        range_ = h - l
        if range_ <= 0:
            return FeatureScore("Candle Structure", 50, 50, "Flat candle")
        # Bullish engulfing
        if c > o and pc < po and c > po and o < pc:
            return FeatureScore("Candle Structure", 90, 15, "Bullish engulfing")
        # Bearish engulfing
        if c < o and pc > po and c < po and o > pc:
            return FeatureScore("Candle Structure", 15, 90, "Bearish engulfing")
        # Hammer
        if lower_wick > body * 2 and upper_wick < body * 0.5:
            return FeatureScore("Candle Structure", 80, 25, "Hammer / bullish rejection")
        # Shooting star
        if upper_wick > body * 2 and lower_wick < body * 0.5:
            return FeatureScore("Candle Structure", 25, 80, "Shooting star / bearish rejection")
        if c > o:
            return FeatureScore("Candle Structure", 60, 40, "Bullish candle")
        if c < o:
            return FeatureScore("Candle Structure", 40, 60, "Bearish candle")
        return FeatureScore("Candle Structure", 50, 50, "Doji/neutral")

    @staticmethod
    def _score_bos(bos: str) -> FeatureScore:
        if bos == "BULLISH_BOS":
            return FeatureScore("BOS", 85, 20, "Bullish break of structure")
        if bos == "BEARISH_BOS":
            return FeatureScore("BOS", 20, 85, "Bearish break of structure")
        return FeatureScore("BOS", 50, 50, "No break of structure")

    @staticmethod
    def _score_choch(choch: str) -> FeatureScore:
        if choch == "BULLISH_CHOCH":
            return FeatureScore("CHOCH", 85, 20, "Bullish change of character")
        if choch == "BEARISH_CHOCH":
            return FeatureScore("CHOCH", 20, 85, "Bearish change of character")
        return FeatureScore("CHOCH", 50, 50, "No change of character")

    @staticmethod
    def aggregate(
        scores: list[FeatureScore],
        weights: dict[str, float] | None = None,
    ) -> tuple[float, float, list[str], list[str]]:
        """Additive model: confidence = aligned_feature_weight / total_weight * 100."""
        if not scores:
            return 0.0, 0.0, [], []

        buy_pts = sell_pts = total_w = 0.0
        buy_reasons: list[str] = []
        sell_reasons: list[str] = []

        for fs in scores:
            w = (weights or {}).get(fs.name, 1.0)
            total_w += w
            # Feature aligned if score >= 60
            if fs.buy_score >= 60:
                buy_pts += w * (fs.buy_score / 100)
                if fs.buy_score >= 70:
                    buy_reasons.append(f"{fs.name}: {fs.reason}")
            if fs.sell_score >= 60:
                sell_pts += w * (fs.sell_score / 100)
                if fs.sell_score >= 70:
                    sell_reasons.append(f"{fs.name}: {fs.reason}")

        if total_w == 0:
            return 0.0, 0.0, [], []

        raw_buy = buy_pts / total_w
        raw_sell = sell_pts / total_w
        return (
            _clamp(raw_buy / 0.57 * 90),
            _clamp(raw_sell / 0.57 * 90),
            buy_reasons,
            sell_reasons,
        )
