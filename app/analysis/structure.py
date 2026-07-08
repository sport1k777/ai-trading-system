import pandas as pd


class StructureAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame):

        if len(df) < 20:
            return "RANGE"

        highs = df["high"].tail(10).tolist()
        lows = df["low"].tail(10).tolist()

        higher_highs = 0
        lower_highs = 0

        higher_lows = 0
        lower_lows = 0

        for i in range(1, len(highs)):

            if highs[i] > highs[i - 1]:
                higher_highs += 1
            else:
                lower_highs += 1

            if lows[i] > lows[i - 1]:
                higher_lows += 1
            else:
                lower_lows += 1

        if higher_highs >= 6 and higher_lows >= 6:
            return "UPTREND"

        if lower_highs >= 6 and lower_lows >= 6:
            return "DOWNTREND"

        return "RANGE"


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    print("\n========== STRUCTURE ==========\n")
    print(StructureAnalyzer.analyze(df))