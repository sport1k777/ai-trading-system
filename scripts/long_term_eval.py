"""
Long-term multi-asset backtest evaluation.
Uses AI Signal Engine (FeatureEngine) + RiskManager.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.analysis.feature_engine import FeatureEngine
from app.config import BACKTEST_MAX_HOLD_BARS, BACKTEST_WARMUP_BARS, MIN_BARS_BETWEEN_TRADES
from app.risk.risk_manager import RiskManager
from app.utils.bybit_client import BybitClient

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
INTERVALS = {"15m": "15", "1h": "60"}
MONTHS = 14  # fetch slightly > 12 months
CACHE_DIR = Path(".cache/longterm")
RISK_PCT = 1.0  # 1% account risk per R


def fetch_history(symbol: str, interval: str, months: int = MONTHS) -> pd.DataFrame:
    cache = CACHE_DIR / f"{symbol}_{interval}.csv"
    if cache.exists():
        df = pd.read_csv(cache, parse_dates=["timestamp"])
        age_hours = (time.time() - cache.stat().st_mtime) / 3600
        if age_hours < 24 and len(df) > 1000:
            return df

    client = BybitClient()
    target_start = datetime.now(timezone.utc) - timedelta(days=months * 30)
    target_ms = int(target_start.timestamp() * 1000)
    end_ms: int | None = None
    chunks: list[pd.DataFrame] = []

    while True:
        kwargs = {
            "category": "linear",
            "symbol": symbol,
            "interval": INTERVALS[interval],
            "limit": 1000,
        }
        if end_ms is not None:
            kwargs["end"] = end_ms

        resp = client.session.get_kline(**kwargs)
        if resp.get("retCode", 0) != 0:
            raise RuntimeError(resp.get("retMsg", "kline error"))

        raw = resp["result"]["list"]
        if not raw:
            break

        batch = pd.DataFrame(
            raw,
            columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
        )
        batch = batch.astype({
            "open": float, "high": float, "low": float, "close": float,
            "volume": float, "turnover": float,
        })
        batch["timestamp"] = pd.to_datetime(batch["timestamp"].astype("int64"), unit="ms")
        chunks.append(batch)

        oldest_ms = int(raw[-1][0])
        if oldest_ms <= target_ms or len(raw) < 1000:
            break
        end_ms = oldest_ms - 1
        time.sleep(0.05)

    if not chunks:
        raise ValueError(f"No data for {symbol} {interval}")

    df = pd.concat(chunks, ignore_index=True)
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    df = df[df["timestamp"] >= pd.Timestamp(target_start.replace(tzinfo=None))]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


def run_backtest(df: pd.DataFrame, symbol: str, interval: str) -> list[dict]:
    from app.analysis.ai_signal_engine import CONFIG_PATH
    df = FeatureEngine.precompute(FeatureEngine.prepare(df))
    threshold = 90.0
    if CONFIG_PATH.exists():
        threshold = float(json.load(open(CONFIG_PATH)).get("threshold", 90))

    trades: list[dict] = []
    last_trade = -MIN_BARS_BETWEEN_TRADES
    end = len(df) - BACKTEST_MAX_HOLD_BARS - 1

    for i in range(BACKTEST_WARMUP_BARS, end):
        if i - last_trade < MIN_BARS_BETWEEN_TRADES:
            continue

        signal = FeatureEngine.signal_at(df, i, threshold)
        if signal["signal"] == "WAIT":
            continue

        entry_idx = i + 1
        if entry_idx >= len(df):
            continue

        entry = float(df.iloc[entry_idx]["open"])
        atr = float(df.iloc[i]["atr"])
        if atr <= 0:
            continue

        setup = signal.get("setup_type", "ai_signal")
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
            tp_price=signal.get("tp_price"), setup_type=setup,
        )

        entry_time = df.iloc[entry_idx]["timestamp"]
        trades.append({
            "symbol": symbol,
            "interval": interval,
            "entry_time": entry_time,
            "signal": signal["signal"],
            "setup": signal.get("setup_type", "ai_signal"),
            "confidence": signal.get("confidence", 0),
            "result": outcome["result"],
            "pnl_r": outcome["pnl_r"],
            "pnl_pct": outcome["pnl_r"] * RISK_PCT,
        })
        last_trade = i

    return trades


def compute_metrics(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}

    r = trades["pnl_r"].values
    wins = trades[trades["result"] == "WIN"]
    losses = trades[trades["result"] == "LOSS"]
    gp = r[r > 0].sum()
    gl = abs(r[r < 0].sum())

    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = float(dd.max())

    expectancy = float(r.mean())
    std_r = float(r.std(ddof=1)) if len(r) > 1 else 0.0

    days = (trades["entry_time"].max() - trades["entry_time"].min()).days or 1
    trades_per_year = len(trades) / (days / 365.25)
    sharpe = (expectancy / std_r * np.sqrt(trades_per_year)) if std_r > 0 else 0.0

    trades["month"] = trades["entry_time"].dt.to_period("M")
    monthly = trades.groupby("month").agg(
        trades=("pnl_r", "count"),
        return_r=("pnl_r", "sum"),
        wins=("result", lambda x: (x == "WIN").sum()),
    )
    monthly["win_rate"] = (monthly["wins"] / monthly["trades"] * 100).round(1)
    monthly["return_pct"] = monthly["return_r"] * RISK_PCT

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": int((trades["result"] == "TIMEOUT").sum()),
        "win_rate": round(len(wins) / len(trades) * 100, 2),
        "profit_factor": round(gp / gl, 2) if gl > 0 else float("inf"),
        "net_profit_r": round(float(r.sum()), 2),
        "net_profit_pct": round(float(r.sum()) * RISK_PCT, 2),
        "max_drawdown_r": round(max_dd, 2),
        "expectancy_r": round(expectancy, 3),
        "sharpe_ratio": round(sharpe, 2),
        "avg_win_r": round(float(wins["pnl_r"].mean()), 2) if len(wins) else 0,
        "avg_loss_r": round(float(abs(losses["pnl_r"].mean())), 2) if len(losses) else 0,
        "days": days,
        "equity_curve": [{"trade": i + 1, "r": round(float(v), 2)} for i, v in enumerate(equity)],
        "monthly": monthly.reset_index().astype({"month": str}).to_dict(orient="records"),
    }


def main():
    all_trades: list[dict] = []
    segment_stats: list[dict] = []

    print("=" * 60)
    print("LONG-TERM BACKTEST EVALUATION")
    print("=" * 60)

    for symbol in SYMBOLS:
        for interval in INTERVALS:
            label = f"{symbol} {interval}"
            print(f"\n[{label}] Fetching data...")
            try:
                df = fetch_history(symbol, interval)
                print(f"  Candles: {len(df)}  ({df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]})")
            except Exception as e:
                print(f"  ERROR fetching: {e}")
                continue

            print(f"  Running backtest...")
            t0 = time.time()
            trades = run_backtest(df, symbol, interval)
            elapsed = time.time() - t0
            print(f"  Trades: {len(trades)}  ({elapsed:.1f}s)")

            all_trades.extend(trades)
            if trades:
                seg = compute_metrics(pd.DataFrame(trades))
                seg["symbol"] = symbol
                seg["interval"] = interval
                segment_stats.append({k: v for k, v in seg.items() if k not in ("equity_curve", "monthly")})

    tdf = pd.DataFrame(all_trades)
    if tdf.empty:
        print("\nNo trades generated.")
        return

    tdf["entry_time"] = pd.to_datetime(tdf["entry_time"])
    combined = compute_metrics(tdf)

    # Trade distribution
    dist = {
        "by_symbol": tdf.groupby("symbol")["pnl_r"].agg(["count", "sum"]).reset_index().to_dict(orient="records"),
        "by_interval": tdf.groupby("interval")["pnl_r"].agg(["count", "sum"]).reset_index().to_dict(orient="records"),
        "by_setup": tdf.groupby("setup")["pnl_r"].agg(["count", "sum"]).reset_index().to_dict(orient="records"),
        "by_direction": tdf.groupby("signal")["pnl_r"].agg(["count", "sum"]).reset_index().to_dict(orient="records"),
        "by_result": tdf.groupby("result")["pnl_r"].agg(["count", "sum"]).reset_index().to_dict(orient="records"),
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": SYMBOLS,
        "intervals": list(INTERVALS.keys()),
        "months_requested": MONTHS,
        "combined": combined,
        "segments": segment_stats,
        "distribution": dist,
    }

    out = Path(".cache/longterm/report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print("\n" + "=" * 60)
    print("COMBINED RESULTS")
    print("=" * 60)
    print(f"Total Trades     : {combined['total_trades']}")
    print(f"Win Rate         : {combined['win_rate']}%")
    print(f"Profit Factor    : {combined['profit_factor']}")
    print(f"Net Profit       : {combined['net_profit_r']}R ({combined['net_profit_pct']}%)")
    print(f"Max Drawdown     : {combined['max_drawdown_r']}R")
    print(f"Sharpe Ratio     : {combined['sharpe_ratio']}")
    print(f"Expectancy       : {combined['expectancy_r']}R/trade")
    print(f"Report saved     : {out}")


if __name__ == "__main__":
    main()
