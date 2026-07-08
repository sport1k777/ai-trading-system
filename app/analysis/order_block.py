import pandas as pd


class OrderBlockAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame):
        if len(df) < 20:
            return None

        bullish = None
        bearish = None

        for i in range(len(df) - 15, 1, -1):
            candle = df.iloc[i]

            if candle["close"] < candle["open"]:
                future_high = df.iloc[i + 1 : i + 6]["high"].max()
                if future_high > candle["high"]:
                    bullish = {
                        "type": "BULLISH",
                        "high": float(candle["high"]),
                        "low": float(candle["low"]),
                        "index": i,
                    }
                    break

        for i in range(len(df) - 15, 1, -1):
            candle = df.iloc[i]

            if candle["close"] > candle["open"]:
                future_low = df.iloc[i + 1 : i + 6]["low"].min()
                if future_low < candle["low"]:
                    bearish = {
                        "type": "BEARISH",
                        "high": float(candle["high"]),
                        "low": float(candle["low"]),
                        "index": i,
                    }
                    break

        if bullish is None and bearish is None:
            return None

        return {
            "bullish": bullish,
            "bearish": bearish,
        }


if __name__ == "__main__":
    from app.collectors.candles import CandleCollector

    collector = CandleCollector()
    df = collector.get_candles()
    print("\n========== ORDER BLOCK ==========\n")
    print(OrderBlockAnalyzer.analyze(df))
