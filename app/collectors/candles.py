from pybit.unified_trading import HTTP
from app.config import BYBIT_API_KEY, BYBIT_API_SECRET

import pandas as pd


class CandleCollector:
    def __init__(self):
        self.session = HTTP(
            testnet=False,
            api_key=BYBIT_API_KEY,
            api_secret=BYBIT_API_SECRET,
        )

    def get_candles(
        self,
        symbol="BTCUSDT",
        interval="15",
        limit=200,
    ):
        response = self.session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit,
        )

        data = response["result"]["list"]

        df = pd.DataFrame(
            data,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
            ],
        )

        df = df.astype(
            {
                "open": float,
                "high": float,
                "low": float,
                "close": float,
                "volume": float,
                "turnover": float,
            }
        )

        df["timestamp"] = pd.to_datetime(
            df["timestamp"].astype("int64"),
            unit="ms",
        )

        df = df.sort_values("timestamp").reset_index(drop=True)

        return df


if __name__ == "__main__":
    collector = CandleCollector()

    df = collector.get_candles()

    print(df.tail())