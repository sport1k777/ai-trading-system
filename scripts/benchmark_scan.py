#!/usr/bin/env python3
"""Benchmark parallel scan throughput for 100/150/200 symbols."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SIGNAL_ENGINE_VERSION", "v2")

import logging

logging.getLogger("app").setLevel(logging.WARNING)

from app.pipeline import TradingPipeline
from app.scanner.parallel_runner import _auto_worker_count, estimate_scan_duration, scan_symbols_parallel


def _mock_scan(symbol: str) -> dict:
    """Lightweight scan stub — measures orchestration overhead only."""
    time.sleep(0.05)
    return {"symbol": symbol, "signal": "WAIT"}


def _live_scan(symbol: str) -> dict:
    pipeline = TradingPipeline()
    started = time.monotonic()
    try:
        result = pipeline.analyze(symbol=symbol, interval="15", limit=120)
        elapsed = time.monotonic() - started
        return {
            "symbol": symbol,
            "signal": result.signal.get("signal"),
            "elapsed": round(elapsed, 3),
        }
    except Exception as exc:
        return {"symbol": symbol, "error": str(exc), "elapsed": time.monotonic() - started}


def benchmark(counts: list[int], *, live: bool = False) -> dict:
    base_symbols = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
        "BNBUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "MATICUSDT",
    ]
    worker_fn = _live_scan if live else _mock_scan
    report: dict = {"mode": "live" if live else "mock", "runs": {}}

    for n in counts:
        symbols = [base_symbols[i % len(base_symbols)] for i in range(n)]
        workers = _auto_worker_count(n)
        started = time.monotonic()
        _, failures = scan_symbols_parallel(symbols, worker_fn, max_workers=workers)
        elapsed = time.monotonic() - started
        report["runs"][str(n)] = {
            "symbols": n,
            "workers": workers,
            "elapsed_seconds": round(elapsed, 2),
            "failures": failures,
            "estimate_seconds": round(estimate_scan_duration(n), 2),
            "cpu_cores": os.cpu_count(),
            "cpu_cap_pct": 80,
        }
        print(f"n={n} workers={workers} elapsed={elapsed:.2f}s failures={failures}")

    out = Path(".cache/benchmark_scan.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"Report written to {out}")
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run real pipeline scans")
    args = parser.parse_args()
    benchmark([100, 150, 200], live=args.live)
