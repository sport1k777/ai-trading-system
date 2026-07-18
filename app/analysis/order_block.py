from __future__ import annotations

import pandas as pd

LOOKBACK = 100


def _distance_to_zone(price: float, low: float, high: float) -> float:
    zone_low = min(low, high)
    zone_high = max(low, high)
    if zone_low <= price <= zone_high:
        return 0.0
    return min(abs(price - zone_low), abs(price - zone_high)) / price


class OrderBlockAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame, *, lookback: int = LOOKBACK):
        if len(df) < 20:
            return None

        price = float(df.iloc[-1]["close"])
        start = max(1, len(df) - lookback)
        bullish = None
        bearish = None
        best_bull_dist = float("inf")
        best_bear_dist = float("inf")

        for i in range(len(df) - 1, start - 1, -1):
            if i + 6 >= len(df):
                continue
            candle = df.iloc[i]

            if candle["close"] < candle["open"]:
                future_high = df.iloc[i + 1 : i + 6]["high"].max()
                if future_high > candle["high"]:
                    low = float(candle["low"])
                    high = float(candle["high"])
                    dist = _distance_to_zone(price, low, high)
                    if dist < best_bull_dist:
                        best_bull_dist = dist
                        bullish = {
                            "type": "BULLISH",
                            "high": high,
                            "low": low,
                            "index": i,
                        }

            if candle["close"] > candle["open"]:
                future_low = df.iloc[i + 1 : i + 6]["low"].min()
                if future_low < candle["low"]:
                    low = float(candle["low"])
                    high = float(candle["high"])
                    dist = _distance_to_zone(price, low, high)
                    if dist < best_bear_dist:
                        best_bear_dist = dist
                        bearish = {
                            "type": "BEARISH",
                            "high": high,
                            "low": low,
                            "index": i,
                        }

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
