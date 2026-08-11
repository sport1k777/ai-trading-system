#!/usr/bin/env python3
"""
Production evaluation pipeline:
  1. Fetch/cache all symbol × timeframe data
  2. Walk-forward robust optimization
  3. Full out-of-sample evaluation
  4. Final production report
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.production_optimizer import (
    INTERVALS,
    PRODUCTION_DIR,
    PRODUCTION_MODEL,
    PRODUCTION_REPORT,
    MIN_SEGMENT_TRADES,
    ProductionOptimizer,
    ModelGenes,
    compute_metrics,
    evaluate_model,
    production_readiness_score,
    SYMBOLS,
)
from app.utils.bybit_client import BybitClient

CACHE_DIR = Path(".cache/longterm")
MONTHS = 14


def fetch_history(symbol: str, interval: str) -> pd.DataFrame | None:
    cache = CACHE_DIR / f"{symbol}_{interval}.csv"
    if cache.exists():
        df = pd.read_csv(cache, parse_dates=["timestamp"])
        if len(df) > 500:
            return df

    client = BybitClient()
    target_start = datetime.now(timezone.utc) - timedelta(days=MONTHS * 30)
    target_ms = int(target_start.timestamp() * 1000)
    end_ms = None
    chunks = []

    for _ in range(60):
        kwargs = {"category": "linear", "symbol": symbol,
                  "interval": INTERVALS[interval], "limit": 1000}
        if end_ms:
            kwargs["end"] = end_ms
        try:
            resp = client.session.get_kline(**kwargs)
        except Exception as e:
            print(f"  Fetch error {symbol} {interval}: {e}")
            return None
        if resp.get("retCode", 0) != 0:
            print(f"  API error {symbol} {interval}: {resp.get('retMsg')}")
            return None
        raw = resp["result"]["list"]
        if not raw:
            break
        batch = pd.DataFrame(raw, columns=[
            "timestamp", "open", "high", "low", "close", "volume", "turnover",
        ]).astype({"open": float, "high": float, "low": float, "close": float,
                   "volume": float, "turnover": float})
        batch["timestamp"] = pd.to_datetime(batch["timestamp"].astype("int64"), unit="ms")
        chunks.append(batch)
        oldest_ms = int(raw[-1][0])
        if oldest_ms <= target_ms or len(raw) < 1000:
            break
        end_ms = oldest_ms - 1
        time.sleep(0.05)

    if not chunks:
        return None
    df = pd.concat(chunks, ignore_index=True)
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


def fetch_all():
    print("=" * 60)
    print("FETCHING DATA")
    print("=" * 60)
    loaded = 0
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            label = f"{symbol} {interval}"
            path = CACHE_DIR / f"{symbol}_{interval}.csv"
            if path.exists() and len(pd.read_csv(path)) > 500:
                print(f"  {label}: cached")
                loaded += 1
                continue
            print(f"  {label}: fetching...")
            df = fetch_history(symbol, interval)
            if df is not None:
                print(f"    {len(df)} candles")
                loaded += 1
            else:
                print(f"    FAILED")
    print(f"Loaded {loaded}/{len(SYMBOLS) * len(INTERVALS)} datasets\n")
    return loaded


def build_report(
    optimizer: ProductionOptimizer,
    full_seg: list[dict],
    oos_seg: list[dict],
    full_combined: dict,
    oos_combined: dict,
) -> dict:
    by_symbol: dict[str, list] = {}
    by_interval: dict[str, list] = {}
    for m in full_seg:
        by_symbol.setdefault(m["symbol"], []).append(m)
        by_interval.setdefault(m["interval"], []).append(m)

    sym_summary = []
    for sym in SYMBOLS:
        segs = by_symbol.get(sym, [])
        if not segs:
            sym_summary.append({"symbol": sym, "status": "no_data"})
            continue
        trades = sum(s["total_trades"] for s in segs)
        pf_vals = [s["profit_factor"] for s in segs if s["total_trades"] >= MIN_SEGMENT_TRADES]
        sym_summary.append({
            "symbol": sym,
            "segments": len(segs),
            "total_trades": trades,
            "avg_profit_factor": round(float(np.mean(pf_vals)), 2) if pf_vals else 0,
            "min_profit_factor": round(min(pf_vals), 2) if pf_vals else 0,
            "net_profit_r": round(sum(s["net_profit_r"] for s in segs), 2),
        })

    tf_summary = []
    for iv in INTERVALS:
        segs = by_interval.get(iv, [])
        pf_vals = [s["profit_factor"] for s in segs if s["total_trades"] >= MIN_SEGMENT_TRADES]
        tf_summary.append({
            "timeframe": iv,
            "segments": len(segs),
            "total_trades": sum(s["total_trades"] for s in segs),
            "avg_profit_factor": round(float(np.mean(pf_vals)), 2) if pf_vals else 0,
            "net_profit_r": round(sum(s["net_profit_r"] for s in segs), 2),
        })

    expected = len(SYMBOLS) * len(INTERVALS)
    readiness, weaknesses = production_readiness_score(
        oos_seg, oos_combined, len(optimizer.segments), expected,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": optimizer.best.to_dict() if optimizer.best else {},
        "walk_forward": {
            "train_ratio": 0.70,
            "fitness": optimizer.best_fitness,
        },
        "overall_full_sample": full_combined,
        "overall_oos": oos_combined,
        "by_symbol": sym_summary,
        "by_timeframe": tf_summary,
        "segment_details": full_seg,
        "oos_segment_details": oos_seg,
        "production_readiness_score": readiness,
        "weaknesses": weaknesses,
        "targets": {
            "profit_factor": 1.5,
            "positive_expectancy": oos_combined.get("expectancy_r", 0) > 0,
            "controlled_drawdown": oos_combined.get("max_drawdown_r", 999) < 50,
        },
    }


def print_report(report: dict):
    print("\n" + "=" * 60)
    print("FINAL PRODUCTION REPORT")
    print("=" * 60)

    oos = report["overall_oos"]
    full = report["overall_full_sample"]
    print("\n--- OVERALL (Out-of-Sample 30%) ---")
    print(f"Total Trades     : {oos['total_trades']}")
    print(f"Win Rate         : {oos['win_rate']}%")
    print(f"Profit Factor    : {oos['profit_factor']}")
    print(f"Average RR       : {oos['avg_rr']} R")
    print(f"Max Drawdown     : {oos['max_drawdown_r']} R")
    print(f"Expectancy       : {oos['expectancy_r']} R/trade")
    print(f"Net Profit       : {oos['net_profit_r']} R")

    print("\n--- OVERALL (Full Sample) ---")
    print(f"Total Trades     : {full['total_trades']}")
    print(f"Profit Factor    : {full['profit_factor']}")
    print(f"Net Profit       : {full['net_profit_r']} R")

    print("\n--- BY SYMBOL ---")
    for s in report["by_symbol"]:
        if s.get("status") == "no_data":
            print(f"  {s['symbol']:10s}: NO DATA")
        else:
            print(f"  {s['symbol']:10s}: trades={s['total_trades']:4d}  "
                  f"avgPF={s['avg_profit_factor']:.2f}  minPF={s['min_profit_factor']:.2f}  "
                  f"net={s['net_profit_r']:+.1f}R")

    print("\n--- BY TIMEFRAME ---")
    for t in report["by_timeframe"]:
        print(f"  {t['timeframe']:4s}: segments={t['segments']}  "
              f"trades={t['total_trades']:4d}  avgPF={t['avg_profit_factor']:.2f}  "
              f"net={t['net_profit_r']:+.1f}R")

    print("\n--- SEGMENT DETAILS (Full) ---")
    for m in report["segment_details"]:
        print(f"  {m['symbol']:10s} {m['interval']:4s}: "
              f"trades={m['total_trades']:4d} WR={m['win_rate']:5.1f}% "
              f"PF={m['profit_factor']:.2f} net={m['net_profit_r']:+.1f}R DD={m['max_drawdown_r']:.1f}R")

    print(f"\n--- PRODUCTION READINESS: {report['production_readiness_score']}/100 ---")
    if report["weaknesses"]:
        print("\nRemaining weaknesses:")
        for w in report["weaknesses"]:
            print(f"  - {w}")
    print(f"\nReport saved: {PRODUCTION_REPORT}")
    print("=" * 60)


def main():
    import sys
    skip_fetch = "--skip-fetch" in sys.argv
    if not skip_fetch:
        fetch_all()
    else:
        print("Skipping fetch — using cached data only\n")

    opt = ProductionOptimizer()
    opt.load_segments(CACHE_DIR)
    if len(opt.segments) < 3:
        print("ERROR: Not enough data segments loaded.")
        sys.exit(1)

    print("=" * 60)
    print("WALK-FORWARD ROBUST OPTIMIZATION")
    print("=" * 60)
    t0 = time.time()
    best = opt.optimize(grid_phase=True, genetic_generations=50, patience=15)
    print(f"\nOptimization done in {time.time()-t0:.0f}s")

    if not best:
        print("WARNING: Using saved model as fallback.")
        best = opt._base_genes()

    opt.save_production_model()

    full_seg, full_trades = evaluate_model(opt.segments, best, mode="full")
    oos_seg, oos_trades = evaluate_model(opt.segments, best, mode="oos")
    full_combined = compute_metrics(full_trades)
    oos_combined = compute_metrics(oos_trades)

    report = build_report(opt, full_seg, oos_seg, full_combined, oos_combined)
    PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)
    with open(PRODUCTION_REPORT, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print_report(report)


if __name__ == "__main__":
    main()
