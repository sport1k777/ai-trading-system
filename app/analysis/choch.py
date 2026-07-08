from app.analysis.swing import SwingAnalyzer


class CHOCHAnalyzer:

    @staticmethod
    def analyze(df):

        highs, lows = SwingAnalyzer.analyze(df)

        if len(highs) < 2 or len(lows) < 2:
            return "NO_CHOCH"

        prev_high = highs[-2]["price"]
        last_high = highs[-1]["price"]

        prev_low = lows[-2]["price"]
        last_low = lows[-1]["price"]

        last_close = df.iloc[-1]["close"]

        # Зміна структури вгору
        if (
            last_high > prev_high
            and last_low > prev_low
            and last_close > prev_high
        ):
            return "BULLISH_CHOCH"

        # Зміна структури вниз
        if (
            last_high < prev_high
            and last_low < prev_low
            and last_close < prev_low
        ):
            return "BEARISH_CHOCH"

        return "NO_CHOCH"


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    print("\n========== CHOCH ==========\n")
    print(CHOCHAnalyzer.analyze(df))