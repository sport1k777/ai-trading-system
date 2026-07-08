import pandas as pd

from app.analysis.swing import SwingAnalyzer
from app.indicators.signals import SignalIndicators
from app.indicators.trend import TrendAnalyzer

LOOKBACK = 100


class SignalGenerator:
    """
    Regime-adaptive strategy optimized via walk-forward backtesting.

    Setup A — Mean reversion (ADX <= 26): fade BB extremes in ranging markets.
    Setup B — Trend pullback (26 < ADX < 38): enter pullbacks to EMA20 with the trend.
    Setup C — Momentum (ADX >= 38): only when RSI is NOT exhausted (avoid capitulation).
    """

    REQUIRED = (
        "ema20", "ema50", "ema200", "rsi", "macd_diff", "macd_diff_prev",
        "atr", "adx", "bb_upper", "bb_mid", "bb_lower",
    )

    @staticmethod
    def _ready(last: pd.Series) -> bool:
        return all(pd.notna(last[c]) for c in SignalGenerator.REQUIRED)

    @staticmethod
    def generate(df: pd.DataFrame, *, indicators_calculated: bool = False):
        if len(df) < 50:
            return SignalGenerator._wait("Insufficient candle history")

        if not indicators_calculated:
            df = SignalIndicators.calculate(df)

        last = df.iloc[-1]
        prev = df.iloc[-2]
        price = float(last["close"])

        if not SignalGenerator._ready(last):
            return SignalGenerator._wait("Indicators not ready")

        view = df.iloc[-LOOKBACK:] if len(df) > LOOKBACK else df
        trend = TrendAnalyzer.detect_trend(df)
        swing_highs, swing_lows = SwingAnalyzer.analyze(view, lookback=50)

        adx = float(last["adx"])
        rsi = float(last["rsi"])
        prev_rsi = float(prev["rsi"])
        macd = float(last["macd_diff"])
        macd_prev = float(last["macd_diff_prev"])
        ema20, ema50 = float(last["ema20"]), float(last["ema50"])
        bb_u, bb_m, bb_l = float(last["bb_upper"]), float(last["bb_mid"]), float(last["bb_lower"])

        meta = dict(
            trend=trend, structure="RANGE", bos="NO_BOS", choch="NO_CHOCH",
            liquidity=None, orderblock=None, fvg=None,
            swing_highs=swing_highs, swing_lows=swing_lows,
            setup_type="none", tp_price=None,
        )

        micro_bull = ema20 > ema50 and price > ema50
        micro_bear = ema20 < ema50 and price < ema50

        # ── A: Mean reversion (highest win rate) ──
        if adx <= 26:
            if rsi < 40 and price <= bb_l * 1.003 and macd > macd_prev and prev_rsi <= rsi:
                meta["setup_type"] = "mean_reversion"
                meta["tp_price"] = bb_m
                return SignalGenerator._sig(
                    "BUY", 8,
                    ["Range fade: oversold at lower BB", f"RSI={rsi:.0f} ADX={adx:.0f}"],
                    **meta,
                )
            if rsi > 60 and price >= bb_u * 0.997 and macd < macd_prev and prev_rsi >= rsi:
                meta["setup_type"] = "mean_reversion"
                meta["tp_price"] = bb_m
                return SignalGenerator._sig(
                    "SELL", 8,
                    ["Range fade: overbought at upper BB", f"RSI={rsi:.0f} ADX={adx:.0f}"],
                    **meta,
                )

        # ── B: Trend pullback (mid ADX) ──
        if 26 < adx < 38:
            if (
                micro_bull
                and float(last["low"]) <= ema20 * 1.005
                and price >= ema50 * 0.995
                and 38 <= rsi <= 52
                and rsi > prev_rsi
                and macd > macd_prev
            ):
                meta["setup_type"] = "pullback"
                return SignalGenerator._sig(
                    "BUY", 7,
                    ["Trend pullback to EMA20", f"ADX={adx:.0f}"],
                    **meta,
                )
            if (
                micro_bear
                and float(last["high"]) >= ema20 * 0.995
                and price <= ema50 * 1.005
                and 48 <= rsi <= 62
                and rsi < prev_rsi
                and macd < macd_prev
            ):
                meta["setup_type"] = "pullback"
                return SignalGenerator._sig(
                    "SELL", 7,
                    ["Trend pullback to EMA20", f"ADX={adx:.0f}"],
                    **meta,
                )

        # ── C: Momentum (strong trend, avoid exhausted RSI) ──
        if adx >= 38:
            if (
                micro_bear
                and 30 <= rsi <= 46
                and macd < 0
                and macd <= macd_prev
                and price < ema20
                and price < bb_m
            ):
                meta["setup_type"] = "momentum"
                return SignalGenerator._sig(
                    "SELL", 8,
                    ["Strong bearish momentum", f"ADX={adx:.0f} RSI={rsi:.0f}"],
                    **meta,
                )
            if (
                micro_bull
                and 54 <= rsi <= 70
                and macd > 0
                and macd >= macd_prev
                and price > ema20
                and price > bb_m
            ):
                meta["setup_type"] = "momentum"
                return SignalGenerator._sig(
                    "BUY", 8,
                    ["Strong bullish momentum", f"ADX={adx:.0f} RSI={rsi:.0f}"],
                    **meta,
                )

        return SignalGenerator._wait("No qualifying setup", **meta)

    @staticmethod
    def _sig(direction, pts, reasons, **meta):
        return {
            "signal": direction,
            "score": pts if direction == "BUY" else -pts,
            "confluence": pts,
            "setup_type": meta.get("setup_type"),
            "tp_price": meta.get("tp_price"),
            "reasons": reasons,
            "trend": meta["trend"],
            "structure": meta["structure"],
            "bos": meta["bos"],
            "choch": meta["choch"],
            "liquidity": meta["liquidity"],
            "orderblock": meta["orderblock"],
            "fvg": meta["fvg"],
            "swing_highs": meta["swing_highs"],
            "swing_lows": meta["swing_lows"],
        }

    @staticmethod
    def _wait(reason, **meta):
        return {
            "signal": "WAIT", "score": 0, "confluence": 0,
            "setup_type": "none", "tp_price": None,
            "trend": "SIDEWAYS", "structure": "RANGE",
            "bos": "NO_BOS", "choch": "NO_CHOCH",
            "liquidity": None, "orderblock": None, "fvg": None,
            "swing_highs": [], "swing_lows": [],
            "reasons": [reason],
        }
