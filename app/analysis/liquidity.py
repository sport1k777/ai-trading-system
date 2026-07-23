from __future__ import annotations

import pandas as pd

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.analysis.market_context import MarketContext


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
                "source": "bar_sweep",
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
                "source": "bar_sweep",
            }

        return None

    @staticmethod
    def resolve(ctx: MarketContext) -> dict | None:
        """Bar sweep first, then pool proximity (same rules as diagnostic/regime gates)."""
        bar_sweep = LiquidityAnalyzer.analyze(ctx.view)
        if bar_sweep:
            return bar_sweep

        from app.analysis.pro_v2.liquidity_pools import detect_liquidity_pools

        pools = detect_liquidity_pools(ctx)
        price = ctx.price
        if pools["buy_side_pools"]:
            level = max(pools["buy_side_pools"])
            if price < level:
                return {
                    "type": "BUY_SIDE_SWEEP",
                    "level": float(level),
                    "price": float(price),
                    "source": "pool_proximity",
                }
        if pools["sell_side_pools"]:
            level = min(pools["sell_side_pools"])
            if price > level:
                return {
                    "type": "SELL_SIDE_SWEEP",
                    "level": float(level),
                    "price": float(price),
                    "source": "pool_proximity",
                }
        return None


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    liquidity = LiquidityAnalyzer.analyze(df)

    print("\n========== LIQUIDITY ==========\n")
    print(liquidity)