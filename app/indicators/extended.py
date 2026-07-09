"""Extended indicators: VWAP, volume profile, momentum, volatility regime."""

import numpy as np
import pandas as pd


class ExtendedIndicators:

    @staticmethod
    def add_vwap(df: pd.DataFrame, session_bars: int = 96) -> pd.DataFrame:
        """Rolling session VWAP (default ~24h on 15m bars)."""
        tp = (df["high"] + df["low"] + df["close"]) / 3
        vol = df["volume"].replace(0, np.nan)
        cum_vol = vol.rolling(session_bars, min_periods=1).sum()
        cum_tp_vol = (tp * vol).rolling(session_bars, min_periods=1).sum()
        df["vwap"] = cum_tp_vol / cum_vol
        return df

    @staticmethod
    def add_volume_profile(df: pd.DataFrame, lookback: int = 50, bins: int = 12) -> pd.DataFrame:
        """Fast volume profile: POC = VWAP of lookback, VAH/VAL = rolling high/low."""
        tp = (df["high"] + df["low"] + df["close"]) / 3
        vol = df["volume"].replace(0, np.nan)
        df["poc"] = (tp * vol).rolling(lookback, min_periods=10).sum() / vol.rolling(lookback, min_periods=10).sum()
        df["vah"] = df["high"].rolling(lookback, min_periods=10).max()
        df["val"] = df["low"].rolling(lookback, min_periods=10).min()
        return df

    @staticmethod
    def add_momentum(df: pd.DataFrame) -> pd.DataFrame:
        df["roc_10"] = df["close"].pct_change(10) * 100
        df["roc_20"] = df["close"].pct_change(20) * 100
        df["momentum_score"] = (df["roc_10"] + df["roc_20"]) / 2
        return df

    @staticmethod
    def add_volatility_regime(df: pd.DataFrame) -> pd.DataFrame:
        df["atr_sma"] = df["atr"].rolling(20).mean()
        df["vol_regime"] = df["atr"] / df["atr_sma"]
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"] * 100
        return df

    @staticmethod
    def calculate(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df = ExtendedIndicators.add_vwap(df)
        df = ExtendedIndicators.add_volume_profile(df)
        df = ExtendedIndicators.add_momentum(df)
        df = ExtendedIndicators.add_volatility_regime(df)
        return df
