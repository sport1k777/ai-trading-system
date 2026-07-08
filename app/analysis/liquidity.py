import pandas as pd


class LiquidityAnalyzer:

    @staticmethod
    def analyze(df: pd.DataFrame, lookback: int = 20):

        if len(df) < lookback + 5:
            return None

        highs = df["high"]
        lows = df["low"]

        recent_high = highs.iloc[-lookback:].max()
        recent_low = lows.iloc[-lookback:].min()

        last_close = df.iloc[-1]["close"]
        last_high = df.iloc[-1]["high"]
        last_low = df.iloc[-1]["low"]

        # Buy Side Liquidity Sweep
        if (
            last_high >= recent_high
            and last_close < recent_high
        ):
            return {
                "type": "BUY_SIDE_SWEEP",
                "level": float(recent_high),
                "price": float(last_high),
            }

        # Sell Side Liquidity Sweep
        if (
            last_low <= recent_low
            and last_close > recent_low
        ):
            return {
                "type": "SELL_SIDE_SWEEP",
                "level": float(recent_low),
                "price": float(last_low),
            }

        return None


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    liquidity = LiquidityAnalyzer.analyze(df)

    print("\n========== LIQUIDITY ==========\n")
    print(liquidity)