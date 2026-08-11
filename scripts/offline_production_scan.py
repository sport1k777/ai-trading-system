#!/usr/bin/env python3
"""Offline production-like scan using synthetic OHLCV — no Bybit API required."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

import os

os.environ["SIGNAL_ENGINE_VERSION"] = "v2"

from app.config import FAST_SCAN_CANDIDATE_COUNT, SCANNER_SYMBOL_TARGET
from app.indicators.extended import ExtendedIndicators
from app.indicators.signals import SignalIndicators
from app.pipeline import TradingPipeline
from app.scanner.fast_scanner import rank_symbols, score_from_df
from app.validation import validate_signal


def _synthetic_df(symbol: str, *, trend: str = "up", seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed + hash(symbol) % 10000)
    n = 120
    base = 100.0 + (hash(symbol) % 500) / 10.0
    drift = 0.08 if trend == "up" else -0.08 if trend == "down" else 0.0
    closes = base + np.cumsum(rng.normal(drift, 0.5, n))
    highs = closes + rng.uniform(0.1, 0.8, n)
    lows = closes - rng.uniform(0.1, 0.8, n)
    opens = closes + rng.normal(0, 0.2, n)
    volumes = rng.uniform(800, 2000, n)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-07-01", periods=n, freq="15min"),
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


def main() -> dict:
    # Simulate 150-symbol universe
    symbols = [f"SYM{i}USDT" for i in range(150)]
    # Inject known liquid names at front
    symbols[:5] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]

    print("=" * 60)
    print("OFFLINE PRODUCTION-LIKE SCAN (synthetic data)")
    print("=" * 60)
    print(f"Simulated universe:    {len(symbols)}")
    print(f"Configured target:     {SCANNER_SYMBOL_TARGET}")
    print(f"Fast scan top_n:         {FAST_SCAN_CANDIDATE_COUNT}")

    def fast_fn(sym: str):
        trend = "up" if hash(sym) % 3 == 0 else "down" if hash(sym) % 3 == 1 else "flat"
        df = _synthetic_df(sym, trend=trend)
        df = SignalIndicators.add_all(df)
        df = ExtendedIndicators.add_all(df)
        return score_from_df(sym, df)

    candidates = rank_symbols(symbols, fast_fn, top_n=FAST_SCAN_CANDIDATE_COUNT)
    print(f"Fast scan candidates:  {len(candidates)}")

    pipeline = TradingPipeline()
    wait = buy = sell = 0
    val_pass = val_fail = 0
    reasons: Counter = Counter()

    for sym in candidates:
        trend = "up" if hash(sym) % 3 == 0 else "down" if hash(sym) % 3 == 1 else "flat"
        df = _synthetic_df(sym, trend=trend)
        try:
            result = pipeline.analyze(symbol=sym, interval="15", limit=120, df=df)
        except Exception as exc:
            reasons[f"error:{exc}"] += 1
            continue

        direction = result.signal.get("signal", "WAIT")
        if direction == "WAIT":
            wait += 1
            reasons[(result.signal.get("explanation") or "wait")[:60]] += 1
        elif direction == "BUY":
            buy += 1
        elif direction == "SELL":
            sell += 1

        if direction in ("BUY", "SELL") and result.risk:
            v = validate_signal(result, min_confidence=0)
            if v.ok:
                val_pass += 1
            else:
                val_fail += 1
                for e in v.errors:
                    reasons[e[:80]] += 1

    report = {
        "mode": "offline_synthetic",
        "universe": len(symbols),
        "fast_candidates": len(candidates),
        "deep_analyzed": len(candidates),
        "wait": wait,
        "buy": buy,
        "sell": sell,
        "validation_pass": val_pass,
        "validation_fail": val_fail,
        "top_reasons": dict(reasons.most_common(10)),
    }

    print(f"Deep analyzed:         {len(candidates)}")
    print(f"WAIT:                  {wait}")
    print(f"BUY:                   {buy}")
    print(f"SELL:                  {sell}")
    print(f"Validation PASS:       {val_pass}")
    print(f"Validation FAIL:       {val_fail}")
    print("Top reasons:")
    for r, c in reasons.most_common(8):
        print(f"  [{c}x] {r}")

    out = Path(".cache/offline_production_scan.json")
    out.write_text(json.dumps(report, indent=2))
    print(f"\nReport: {out}")
    return report


if __name__ == "__main__":
    main()
