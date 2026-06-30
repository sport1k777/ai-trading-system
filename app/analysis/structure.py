import pandas as pd


class StructureAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame):

        highs = df["high"].tolist()
        lows = df["low"].tolist()

        last_high = highs[-1]
        prev_high = highs[-2]

        last_low = lows[-1]
        prev_low = lows[-2]

        if last_high > prev_high and last_low > prev_low:
            return "UPTREND"

        elif last_high < prev_high and last_low < prev_low:
            return "DOWNTREND"

        else:
            return "RANGE"


if __name__ == "__main__":

     from app.collectors.candles import CandleCollector

     collector = CandleCollector()

     df = collector.get_candles()

     structure = StructureAnalyzer.analyze(df)

     print()
     print("======================")
     print("Market Structure")
     print("======================")
     print(structure)