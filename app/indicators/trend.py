import pandas as pd


class TrendAnalyzer:

    @staticmethod
    def detect_trend(df: pd.DataFrame):

        if len(df) < 200:
            return "SIDEWAYS"

        last = df.iloc[-1]

        ema20 = last["ema20"]
        ema50 = last["ema50"]
        ema200 = last["ema200"]

        if ema20 > ema50 > ema200:
            return "BULLISH"

        if ema20 < ema50 < ema200:
            return "BEARISH"

        return "SIDEWAYS"


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector
    from app.indicators.signals import SignalIndicators

    collector = CandleCollector()

    df = collector.get_candles()

    df = SignalIndicators.calculate(df)

    print("\n========== TREND ==========\n")
    print(TrendAnalyzer.detect_trend(df))