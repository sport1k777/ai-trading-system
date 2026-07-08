import pandas as pd


class OrderBlockAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame):

        if len(df) < 20:
            return None

        last_close = df.iloc[-1]["close"]

        bullish = None
        bearish = None

        # Шукаємо останній Bearish Order Block
        # (остання червона свічка перед сильним ростом)

        for i in range(len(df) - 15, 1, -1):

            candle = df.iloc[i]

            if candle["close"] < candle["open"]:

                future_high = df.iloc[i + 1:i + 6]["high"].max()

                if future_high > candle["high"]:

                    bullish = {
                        "type": "BULLISH",
                        "high": float(candle["high"]),
                        "low": float(candle["low"]),
                        "index": i
                    }

                    break

        # Шукаємо останній Bullish Order Block
        # (остання зелена свічка перед сильним падінням)

        for i in range(len(df) - 15, 1, -1):

            candle = df.iloc[i]

            if candle["close"] > candle["open"]:

                future_low = df.iloc[i + 1:i + 6]["low"].min()

                if future_low < candle["low"]:

                    bearish = {
                        "type": "BEARISH",
                        "high": float(candle["high"]),
                        "low": float(candle["low"]),
                        "index": i
                    }

                    break

        return {
            "bullish": bullish,
            "bearish": bearish
        }


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    result = OrderBlockAnalyzer.analyze(df)

    print("\n========== ORDER BLOCK ==========\n")
    print(result)