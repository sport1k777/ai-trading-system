import pandas as pd

from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange


class SignalIndicators:

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # ==========================
        # EMA
        # ==========================

        df["ema20"] = EMAIndicator(
            close=df["close"],
            window=20,
        ).ema_indicator()

        df["ema50"] = EMAIndicator(
            close=df["close"],
            window=50,
        ).ema_indicator()

        df["ema200"] = EMAIndicator(
            close=df["close"],
            window=200,
        ).ema_indicator()

        # ==========================
        # RSI
        # ==========================

        df["rsi"] = RSIIndicator(
            close=df["close"],
            window=14,
        ).rsi()

        # ==========================
        # MACD
        # ==========================

        macd = MACD(close=df["close"])

        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_diff"] = macd.macd_diff()

        # ==========================
        # ATR
        # ==========================

        atr = AverageTrueRange(
            high=df["high"],
            low=df["low"],
            close=df["close"],
        )

        df["atr"] = atr.average_true_range()

        return df


if __name__ == "__main__":
    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    df = SignalIndicators.calculate(df)

    print(df.tail())

    print("\n========== INDICATORS ==========")
    print(f"EMA20 : {df.iloc[-1]['ema20']:.2f}")
    print(f"EMA50 : {df.iloc[-1]['ema50']:.2f}")
    print(f"EMA200: {df.iloc[-1]['ema200']:.2f}")
    print(f"RSI   : {df.iloc[-1]['rsi']:.2f}")
    print(f"MACD  : {df.iloc[-1]['macd']:.4f}")
    print(f"ATR   : {df.iloc[-1]['atr']:.2f}")