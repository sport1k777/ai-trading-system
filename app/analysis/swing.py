import pandas as pd


class SwingAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame, window: int = 3):

        highs = []
        lows = []

        if len(df) < window * 2 + 1:
            return highs, lows

        for i in range(window, len(df) - window):

            current_high = df.iloc[i]["high"]
            current_low = df.iloc[i]["low"]

            left_highs = df.iloc[i - window:i]["high"]
            right_highs = df.iloc[i + 1:i + window + 1]["high"]

            left_lows = df.iloc[i - window:i]["low"]
            right_lows = df.iloc[i + 1:i + window + 1]["low"]

            # Swing High
            if (
                current_high > left_highs.max()
                and current_high > right_highs.max()
            ):
                highs.append({
                    "index": i,
                    "price": float(current_high),
                    "time": df.iloc[i]["timestamp"]
                })

            # Swing Low
            if (
                current_low < left_lows.min()
                and current_low < right_lows.min()
            ):
                lows.append({
                    "index": i,
                    "price": float(current_low),
                    "time": df.iloc[i]["timestamp"]
                })

        return highs, lows


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    highs, lows = SwingAnalyzer.analyze(df)

    print("\n========== LAST SWING HIGHS ==========\n")

    for h in highs[-5:]:
        print(h)

    print("\n========== LAST SWING LOWS ==========\n")

    for l in lows[-5:]:
        print(l)