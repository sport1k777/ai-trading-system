import pandas as pd


class BOSAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame):

        highs = df["high"]
        lows = df["low"]

        last_high = highs.iloc[-1]
        prev_high = highs.iloc[-2]

        last_low = lows.iloc[-1]
        prev_low = lows.iloc[-2]

        if last_high > prev_high and last_low > prev_low:
            return "BULLISH_BOS"

        elif last_high < prev_high and last_low < prev_low:
            return "BEARISH_BOS"

        else:
            return "NO_BOS"


if __name__ == "__main__":

     from app.collectors.candles import CandleCollector

     collector = CandleCollector()

     df = collector.get_candles()

     bos = BOSAnalyzer.analyze(df)

     print("\n========== BOS ==========")
     print(bos)