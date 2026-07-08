import pandas as pd


class TrendAnalyzer:

    @staticmethod
    def detect_trend(df: pd.DataFrame) -> str:
        if len(df) < 200:
            return "SIDEWAYS"

        last = df.iloc[-1]
        close = float(last["close"])
        ema20 = float(last["ema20"])
        ema50 = float(last["ema50"])
        ema200 = float(last["ema200"])
        slope = float(last["ema20_slope"]) if pd.notna(last["ema20_slope"]) else 0.0

        stack_bull = ema20 > ema50 > ema200
        stack_bear = ema20 < ema50 < ema200

        if ema20 > ema50 and close > ema50:
            return "BULLISH"

        if ema20 < ema50 and close < ema50:
            return "BEARISH"

        if stack_bull and close > ema200:
            return "BULLISH"

        if stack_bear and close < ema200:
            return "BEARISH"

        return "SIDEWAYS"

    @staticmethod
    def is_pullback_to_ema(df: pd.DataFrame, direction: str) -> bool:
        """Price retraced to EMA20-50 value zone in an established trend."""
        last = df.iloc[-1]
        close = float(last["close"])
        ema20 = float(last["ema20"])
        ema50 = float(last["ema50"])
        low = float(last["low"])
        high = float(last["high"])

        zone_top = max(ema20, ema50)
        zone_bottom = min(ema20, ema50)

        if direction == "BULLISH":
            return zone_bottom * 0.998 <= low <= zone_top * 1.002 and close >= ema50

        if direction == "BEARISH":
            return zone_bottom * 0.998 <= high <= zone_top * 1.002 and close <= ema50

        return False
