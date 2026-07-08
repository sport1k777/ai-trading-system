import pandas as pd

from app.analysis.swing import SwingAnalyzer


class StructureAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame) -> str:
        if len(df) < 30:
            return "RANGE"

        highs, lows = SwingAnalyzer.analyze(df, window=3)

        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1]["price"] > highs[-2]["price"]
            hl = lows[-1]["price"] > lows[-2]["price"]
            lh = highs[-1]["price"] < highs[-2]["price"]
            ll = lows[-1]["price"] < lows[-2]["price"]

            if hh and hl:
                return "UPTREND"
            if lh and ll:
                return "DOWNTREND"

        # Fallback: recent candle progression
        highs_tail = df["high"].tail(10).tolist()
        lows_tail = df["low"].tail(10).tolist()

        higher_highs = sum(1 for i in range(1, len(highs_tail)) if highs_tail[i] > highs_tail[i - 1])
        higher_lows = sum(1 for i in range(1, len(lows_tail)) if lows_tail[i] > lows_tail[i - 1])
        lower_highs = sum(1 for i in range(1, len(highs_tail)) if highs_tail[i] < highs_tail[i - 1])
        lower_lows = sum(1 for i in range(1, len(lows_tail)) if lows_tail[i] < lows_tail[i - 1])

        if higher_highs >= 6 and higher_lows >= 6:
            return "UPTREND"
        if lower_highs >= 6 and lower_lows >= 6:
            return "DOWNTREND"

        return "RANGE"
