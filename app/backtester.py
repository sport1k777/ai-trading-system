import logging
import os
from pathlib import Path

import pandas as pd

from app.analysis.signal_generator import SignalGenerator
from app.collectors.candles import CandleCollector
from app.config import (
    BACKTEST_CACHE_PATH,
    BACKTEST_CANDLE_LIMIT,
    BACKTEST_MAX_HOLD_BARS,
    BACKTEST_WARMUP_BARS,
    DEFAULT_INTERVAL,
    DEFAULT_SYMBOL,
    MIN_BARS_BETWEEN_TRADES,
)
from app.indicators.signals import SignalIndicators
from app.risk.risk_manager import RiskManager
from app.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


def _load_candles(collector: CandleCollector) -> pd.DataFrame:
    cache = Path(BACKTEST_CACHE_PATH)
    if cache.exists():
        logger.info("Loading cached candles from %s", cache)
        return pd.read_csv(cache, parse_dates=["timestamp"])

    logger.info("Fetching %s candles from Bybit", BACKTEST_CANDLE_LIMIT)
    df = collector.get_candles(
        symbol=DEFAULT_SYMBOL, interval=DEFAULT_INTERVAL, limit=BACKTEST_CANDLE_LIMIT,
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


class Backtester:

    @staticmethod
    def run(force_refresh: bool = False):
        setup_logging("app.backtester")
        print("\n========== BACKTEST ==========\n")

        if force_refresh and Path(BACKTEST_CACHE_PATH).exists():
            Path(BACKTEST_CACHE_PATH).unlink()

        df = _load_candles(CandleCollector())
        df = SignalIndicators.calculate(df)

        trades: list[dict] = []
        last_trade = -MIN_BARS_BETWEEN_TRADES
        end = len(df) - BACKTEST_MAX_HOLD_BARS - 1

        for i in range(BACKTEST_WARMUP_BARS, end):
            if i - last_trade < MIN_BARS_BETWEEN_TRADES:
                continue

            signal = SignalGenerator.generate(df.iloc[: i + 1], indicators_calculated=True)
            if signal["signal"] == "WAIT":
                continue

            # Enter on next bar open (realistic fill)
            entry_idx = i + 1
            if entry_idx >= len(df):
                continue

            entry = float(df.iloc[entry_idx]["open"])
            atr = float(df.iloc[i]["atr"])
            if atr <= 0:
                continue

            setup = signal.get("setup_type", "trend")
            lows = signal.get("swing_lows") or []
            highs = signal.get("swing_highs") or []
            sl = lows[-1]["price"] if lows else None
            sh = highs[-1]["price"] if highs else None

            future = df.iloc[entry_idx + 1 : entry_idx + 1 + BACKTEST_MAX_HOLD_BARS]
            if future.empty:
                continue

            outcome = RiskManager.simulate_trade(
                signal["signal"], entry, atr, future,
                swing_low=sl, swing_high=sh,
                tp_price=signal.get("tp_price"),
                setup_type=setup,
            )

            trades.append({
                "index": i,
                "signal": signal["signal"],
                "setup": setup,
                "confluence": signal.get("confluence", 0),
                **outcome,
            })
            last_trade = i

        if not trades:
            print("No trades found.")
            return

        wins = sum(1 for t in trades if t["result"] == "WIN")
        losses = sum(1 for t in trades if t["result"] == "LOSS")
        timeouts = sum(1 for t in trades if t["result"] == "TIMEOUT")
        total = len(trades)

        winrate = round(wins / total * 100, 2)
        total_r = round(sum(t["pnl_r"] for t in trades), 2)
        avg_r = round(total_r / total, 3)
        gp = sum(t["pnl_r"] for t in trades if t["pnl_r"] > 0)
        gl = abs(sum(t["pnl_r"] for t in trades if t["pnl_r"] < 0))
        pf = round(gp / gl, 2) if gl > 0 else float("inf")

        equity = peak = max_dd = 0.0
        for t in trades:
            equity += t["pnl_r"]
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)

        setups = {}
        for t in trades:
            s = t.get("setup", "?")
            setups.setdefault(s, {"n": 0, "w": 0})
            setups[s]["n"] += 1
            if t["result"] == "WIN":
                setups[s]["w"] += 1

        print(f"Trades        : {total}")
        print(f"Wins          : {wins}")
        print(f"Losses        : {losses}")
        print(f"Timeouts      : {timeouts}")
        print(f"Win Rate      : {winrate}%")
        print(f"Total R       : {total_r}")
        print(f"Avg R / Trade : {avg_r}")
        print(f"Profit Factor : {pf}")
        print(f"Max Drawdown  : {round(max_dd, 2)} R")
        print("\nBy setup:")
        for name, s in sorted(setups.items()):
            wr = round(s["w"] / s["n"] * 100, 1) if s["n"] else 0
            print(f"  {name:16s}: {s['n']:3d} trades, {wr:5.1f}% win")
        print("\n==============================\n")


if __name__ == "__main__":
    Backtester.run()
