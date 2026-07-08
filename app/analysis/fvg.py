import pandas as pd


class FVGAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame, lookback: int = 80):
        if len(df) < 20:
            return None

        gaps = []
        start = max(2, len(df) - lookback)

        for i in range(start, len(df) - 1):
            c1 = df.iloc[i - 2]
            c2 = df.iloc[i - 1]
            c3 = df.iloc[i]

            if c1["high"] < c3["low"] and c2["close"] > c2["open"]:
                top = float(c3["low"])
                bottom = float(c1["high"])
                filled = any(
                    df.iloc[j]["low"] <= bottom for j in range(i + 1, len(df))
                )
                if not filled:
                    gaps.append(
                        {
                            "type": "BULLISH",
                            "top": top,
                            "bottom": bottom,
                            "size": round(top - bottom, 2),
                            "index": i,
                            "active": True,
                        }
                    )

            elif c1["low"] > c3["high"] and c2["close"] < c2["open"]:
                top = float(c1["low"])
                bottom = float(c3["high"])
                filled = any(
                    df.iloc[j]["high"] >= top for j in range(i + 1, len(df))
                )
                if not filled:
                    gaps.append(
                        {
                            "type": "BEARISH",
                            "top": top,
                            "bottom": bottom,
                            "size": round(top - bottom, 2),
                            "index": i,
                            "active": True,
                        }
                    )

        if not gaps:
            return None

        return gaps[-1]
