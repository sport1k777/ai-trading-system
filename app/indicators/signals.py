import pandas as pd

from ta.trend import ADXIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange, BollingerBands


class SignalIndicators:

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["ema20"] = EMAIndicator(close=df["close"], window=20).ema_indicator()
        df["ema50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
        df["ema200"] = EMAIndicator(close=df["close"], window=200).ema_indicator()

        df["rsi"] = RSIIndicator(close=df["close"], window=14).rsi()

        macd = MACD(close=df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_diff"] = macd.macd_diff()
        df["macd_diff_prev"] = df["macd_diff"].shift(1)

        atr = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"])
        df["atr"] = atr.average_true_range()
        df["atr_pct"] = df["atr"] / df["close"] * 100

        adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14)
        df["adx"] = adx.adx()

        bb = BollingerBands(close=df["close"], window=20, window_dev=2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_mid"] = bb.bollinger_mavg()
        df["bb_lower"] = bb.bollinger_lband()

        df["ema20_slope"] = df["ema20"].pct_change(5) * 100
        df["volume_sma"] = df["volume"].rolling(20).mean()
        df["volume_ratio"] = df["volume"] / df["volume_sma"]

        return df
