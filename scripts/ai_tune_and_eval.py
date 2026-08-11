"""
Auto-tune AI Signal Engine weights via long-term backtest evaluation.
Uses vectorized FeatureEngine for fast iteration on cached data.
"""
from __future__ import annotations

import copy
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.feature_engine import FeatureEngine, CONFIG_PATH, WEIGHTS_PATH, load_config
from app.config import AI_CONFIDENCE_THRESHOLD, AI_FEATURE_WEIGHTS, BACKTEST_MAX_HOLD_BARS, BACKTEST_WARMUP_BARS, MIN_BARS_BETWEEN_TRADES
from app.risk.risk_manager import RiskManager

CACHE_DIR = Path(".cache/longterm")
TUNE_LOG = Path(".cache/ai_tune_log.json")

BASELINE = {
    "net_profit_r": -57.4,
    "profit_factor": 0.93,
    "sharpe_ratio": -1.07,
    "win_rate": 24.11,
    "max_drawdown_r": 135.79,
}

SEGMENTS = [
    ("BTCUSDT", "15m"),
    ("BTCUSDT", "1h"),
    ("ETHUSDT", "15m"),
    ("ETHUSDT", "1h"),
    ("XRPUSDT", "1h"),
]


def _load_df(symbol: str, interval: str) -> pd.DataFrame | None:
    path = CACHE_DIR / f"{symbol}_{interval}.csv"
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["timestamp"])


def run_backtest(df: pd.DataFrame, threshold: float) -> list[dict]:
    df = FeatureEngine.precompute(FeatureEngine.prepare(df))
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

        lows = signal.get("swing_lows") or []
        highs = signal.get("swing_highs") or []
        sl = lows[-1]["price"] if lows else None
        sh = highs[-1]["price"] if highs else None

        future = df.iloc[entry_idx + 1 : entry_idx + 1 + BACKTEST_MAX_HOLD_BARS]
        if future.empty:
            continue

        outcome = RiskManager.simulate_trade(
            signal["signal"], entry, atr, future,
            swing_low=sl, swing_high=sh, setup_type="ai_signal",
        )

        trades.append({
            "signal": signal["signal"],
            "confidence": signal.get("confidence", 0),
            "result": outcome["result"],
            "pnl_r": outcome["pnl_r"],
        })
        last_trade = i

    return trades


def compute_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"total_trades": 0, "net_profit_r": 0, "profit_factor": 0,
                "sharpe_ratio": 0, "win_rate": 0, "max_drawdown_r": 0, "expectancy_r": 0}

    r = np.array([t["pnl_r"] for t in trades])
    wins = [t for t in trades if t["result"] == "WIN"]
    gp = r[r > 0].sum()
    gl = abs(r[r < 0].sum())
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    max_dd = float((peak - equity).max())
    std_r = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    expectancy = float(r.mean())
    sharpe = (expectancy / std_r * np.sqrt(len(trades) / 1.14)) if std_r > 0 else 0.0

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": int((r < 0).sum()),
        "win_rate": round(len(wins) / len(trades) * 100, 2),
        "profit_factor": round(gp / gl, 2) if gl > 0 else float("inf"),
        "net_profit_r": round(float(r.sum()), 2),
        "max_drawdown_r": round(max_dd, 2),
        "expectancy_r": round(expectancy, 3),
        "sharpe_ratio": round(sharpe, 2),
    }


def is_better(metrics: dict) -> bool:
    if metrics["total_trades"] < 50:
        return False
    return (
        metrics["net_profit_r"] > 0
        and metrics["profit_factor"] >= 1.05
        and metrics["sharpe_ratio"] > 0
        and metrics["net_profit_r"] - BASELINE["net_profit_r"] >= 50
    )


def score_fitness(metrics: dict) -> float:
    if metrics["total_trades"] < 20:
        return -999
    return (
        metrics["net_profit_r"] * 2
        + metrics["profit_factor"] * 30
        + metrics["sharpe_ratio"] * 20
        + metrics["win_rate"] * 0.5
        - metrics["max_drawdown_r"] * 0.3
    )


def save_config(threshold: float, weights: dict | None = None):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump({"threshold": threshold}, f)
    if weights:
        with open(WEIGHTS_PATH, "w") as f:
            json.dump(weights, f, indent=2)


def run_full_eval(threshold: float) -> dict:
    all_trades: list[dict] = []
    for symbol, interval in SEGMENTS:
        df = _load_df(symbol, interval)
        if df is None:
            continue
        all_trades.extend(run_backtest(df, threshold))
    return compute_metrics(all_trades)


def tune():
    print("=" * 60)
    print("AI SIGNAL ENGINE — AUTO-TUNE & LONG-TERM EVAL")
    print("=" * 60)
    print(f"Baseline: PF={BASELINE['profit_factor']} Net={BASELINE['net_profit_r']}R Sharpe={BASELINE['sharpe_ratio']}")

    best_threshold = AI_CONFIDENCE_THRESHOLD
    best_metrics = run_full_eval(best_threshold)
    best_fitness = score_fitness(best_metrics)
    log: list[dict] = []

    print(f"\n[Initial] thresh={best_threshold} trades={best_metrics['total_trades']} "
          f"WR={best_metrics['win_rate']}% PF={best_metrics['profit_factor']} "
          f"Net={best_metrics['net_profit_r']}R Sharpe={best_metrics['sharpe_ratio']}")

    # Phase 1: threshold sweep
    print("\n[Phase 1: Threshold sweep]")
    for thresh in [75, 80, 85, 88, 90, 92, 93, 94, 95, 96, 97, 98]:
        t0 = time.time()
        m = run_full_eval(thresh)
        fit = score_fitness(m)
        print(f"  thresh={thresh}: trades={m['total_trades']} PF={m['profit_factor']} "
              f"net={m['net_profit_r']}R sharpe={m['sharpe_ratio']} ({time.time()-t0:.1f}s)")
        log.append({"phase": "threshold", "threshold": thresh, "metrics": m, "fitness": fit})
        if fit > best_fitness:
            best_fitness, best_metrics, best_threshold = fit, m, thresh
        if is_better(m):
            save_config(thresh)
            _save_report(m, thresh)
            return m

    save_config(best_threshold)
    print(f"  Best threshold: {best_threshold}")

    # Phase 2: fine threshold around best
    print("\n[Phase 2: Fine threshold tuning]")
    base = best_threshold
    for delta in [-2, -1, 0, 1, 2]:
        thresh = base + delta
        if thresh < 70 or thresh > 99:
            continue
        m = run_full_eval(thresh)
        fit = score_fitness(m)
        print(f"  thresh={thresh}: trades={m['total_trades']} PF={m['profit_factor']} net={m['net_profit_r']}R")
        if fit > best_fitness:
            best_fitness, best_metrics, best_threshold = fit, m, thresh
        if is_better(m):
            save_config(thresh)
            _save_report(m, thresh)
            return m

    save_config(best_threshold)

    # Phase 3: adjust vector scoring via weight scaling
    print("\n[Phase 3: Weight scaling]")
    for scale_name, scale in [("boost_trend", 1.15), ("boost_mr", 1.25), ("conservative", 1.05)]:
        weights = {k: v * scale for k, v in AI_FEATURE_WEIGHTS.items()}
        save_config(best_threshold, weights)
        m = run_full_eval(best_threshold)
        fit = score_fitness(m)
        print(f"  {scale_name} (x{scale}): trades={m['total_trades']} PF={m['profit_factor']} net={m['net_profit_r']}R")
        if fit > best_fitness:
            best_fitness, best_metrics = fit, m
        if is_better(m):
            _save_report(m, best_threshold)
            return m

    _save_report(best_metrics, best_threshold)
    _save_log(log)

    print("\n" + "=" * 60)
    print("TUNING COMPLETE")
    print("=" * 60)
    print(f"Threshold  : {best_threshold}")
    print(f"Trades     : {best_metrics['total_trades']}")
    print(f"Win Rate   : {best_metrics['win_rate']}%")
    print(f"PF         : {best_metrics['profit_factor']}")
    print(f"Net Profit : {best_metrics['net_profit_r']}R")
    print(f"Sharpe     : {best_metrics['sharpe_ratio']}")
    print(f"Beat baseline: {is_better(best_metrics)}")
    return best_metrics


def _save_report(metrics: dict, threshold: float):
    report = {
        "engine": "AI Signal Engine",
        "threshold": threshold,
        "metrics": metrics,
        "baseline": BASELINE,
        "beat_baseline": is_better(metrics),
    }
    out = Path(".cache/longterm/ai_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved: {out}")


def _save_log(log: list):
    TUNE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(TUNE_LOG, "w") as f:
        json.dump(log, f, indent=2, default=str)


if __name__ == "__main__":
    tune()
