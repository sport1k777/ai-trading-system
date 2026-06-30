import pandas as pd


class SwingAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame):

        highs = []
        lows = []

        for i in range(2, len(df) - 2):

            # Swing High
            if (
                df["high"].iloc[i] > df["high"].iloc[i - 1]
                and df["high"].iloc[i] > df["high"].iloc[i - 2]
                and df["high"].iloc[i] > df["high"].iloc[i + 1]
                and df["high"].iloc[i] > df["high"].iloc[i + 2]
            ):
                highs.append(
                    (
                        df.index[i],
                        float(df["high"].iloc[i])
                    )
                )

            # Swing Low
            if (
                df["low"].iloc[i] < df["low"].iloc[i - 1]
                and df["low"].iloc[i] < df["low"].iloc[i - 2]
                and df["low"].iloc[i] < df["low"].iloc[i + 1]
                and df["low"].iloc[i] < df["low"].iloc[i + 2]
            ):
                lows.append(
                    (
                        df.index[i],
                        float(df["low"].iloc[i])
                    )
                )

        return highs, lows


if __name__ == "__main__":

     from app.collectors.candles import CandleCollector

     collector = CandleCollector()

     df = collector.get_candles()

     highs, lows = SwingAnalyzer.analyze(df)

     print("\n========== SWING HIGHS ==========")

     for h in highs[-5:]:
        print(h)

     print("\n========== SWING LOWS ==========")

     for l in lows[-5:]:
        print(l)