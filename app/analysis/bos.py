import pandas as pd


class BOSAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame) -> str:
        if len(df) < 25:
            return "NO_BOS"

        from app.analysis.swing import SwingAnalyzer

        highs, lows = SwingAnalyzer.analyze(df, window=3)
        last_close = float(df["close"].iloc[-1])

        if len(highs) >= 1:
            last_swing_high = highs[-1]["price"]
            if last_close > last_swing_high:
                return "BULLISH_BOS"

        if len(lows) >= 1:
            last_swing_low = lows[-1]["price"]
            if last_close < last_swing_low:
                return "BEARISH_BOS"

        return "NO_BOS"
