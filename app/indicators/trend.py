import pandas as pd


class TrendAnalyzer:

    @staticmethod
    def add_ema(df: pd.DataFrame) -> pd.DataFrame:

        df = df.copy()

        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

        return df

    @staticmethod
    def detect_trend(df: pd.DataFrame):

        last = df.iloc[-1]

        if last["ema20"] > last["ema50"] > last["ema200"]:
            return "BULLISH"

        if last["ema20"] < last["ema50"] < last["ema200"]:
            return "BEARISH"

        return "SIDEWAYS"


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    analyzer = TrendAnalyzer()

    df = analyzer.add_ema(df)

    print(df.tail())

    print()

    print("Trend:", analyzer.detect_trend(df))