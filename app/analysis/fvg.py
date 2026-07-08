import pandas as pd


class FVGAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame):

        if len(df) < 10:
            return None

        gaps = []

        for i in range(2, len(df)):

            c1 = df.iloc[i - 2]
            c2 = df.iloc[i - 1]
            c3 = df.iloc[i]

            # ---------- Bullish FVG ----------

            if (
                c1["high"] < c3["low"]
                and c2["close"] > c2["open"]
            ):

                gaps.append({
                    "type": "BULLISH",
                    "top": float(c3["low"]),
                    "bottom": float(c1["high"]),
                    "size": float(c3["low"] - c1["high"]),
                    "index": i
                })

            # ---------- Bearish FVG ----------

            elif (
                c1["low"] > c3["high"]
                and c2["close"] < c2["open"]
            ):

                gaps.append({
                    "type": "BEARISH",
                    "top": float(c1["low"]),
                    "bottom": float(c3["high"]),
                    "size": float(c1["low"] - c3["high"]),
                    "index": i
                })

        if not gaps:
            return None

        # Повертаємо найбільший FVG серед останніх
        recent = gaps[-5:]

        return max(recent, key=lambda x: x["size"])


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    gap = FVGAnalyzer.analyze(df)

    print("\n========== FVG ==========\n")
    print(gap)