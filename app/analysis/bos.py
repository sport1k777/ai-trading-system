import pandas as pd


class BOSAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame):

        if len(df) < 20:
            return "NO_BOS"

        highs = df["high"].tail(10).tolist()
        lows = df["low"].tail(10).tolist()

        recent_high = max(highs[:-1])
        recent_low = min(lows[:-1])

        last_close = df["close"].iloc[-1]

        # Bullish BOS
        if last_close > recent_high:
            return "BULLISH_BOS"

        # Bearish BOS
        if last_close < recent_low:
            return "BEARISH_BOS"

        return "NO_BOS"


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    bos = BOSAnalyzer.analyze(df)

    print("\n========== BOS ==========\n")
    print(bos)