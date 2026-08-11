#!/usr/bin/env python3
"""Historical validation — replay engine output and aggregate rejection stats."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SIGNAL_ENGINE_VERSION", "v2")

import logging

logging.getLogger("app").setLevel(logging.WARNING)

from app.config import SCANNER_SYMBOLS
from app.pipeline import TradingPipeline
from app.validation import validate_signal


def run_validation(symbols: list[str] | None = None, *, limit: int = 120) -> dict:
    symbols = symbols or list(SCANNER_SYMBOLS)
    pipeline = TradingPipeline()

    stats = {
        "symbols_scanned": len(symbols),
        "wait": 0,
        "buy": 0,
        "sell": 0,
        "validation_pass": 0,
        "validation_fail": 0,
        "rejection_reasons": Counter(),
        "avg_risk_pct": [],
        "avg_rr_tp1": [],
        "avg_rr_tp2": [],
        "avg_rr_tp3": [],
        "duplicate_tp_failures": 0,
        "invalid_rr_failures": 0,
    }

    for symbol in symbols:
        try:
            result = pipeline.analyze(symbol=symbol, interval="15", limit=limit)
        except Exception as exc:
            stats["rejection_reasons"][f"pipeline_error: {exc}"] += 1
            continue

        direction = result.signal.get("signal")
        if direction == "WAIT":
            stats["wait"] += 1
            reason = result.signal.get("explanation") or result.signal.get("reasons", ["unknown"])[0]
            stats["rejection_reasons"][str(reason)[:80]] += 1
            continue

        if direction == "BUY":
            stats["buy"] += 1
        elif direction == "SELL":
            stats["sell"] += 1

        if not result.risk:
            stats["validation_fail"] += 1
            stats["rejection_reasons"]["no_risk_levels"] += 1
            continue

        v = validate_signal(result, min_confidence=0)
        if v.ok:
            stats["validation_pass"] += 1
            risk = result.risk
            entry = float(risk["entry"])
            stop = float(risk["stop"])
            stats["avg_risk_pct"].append(abs(entry - stop) / entry * 100)
            stats["avg_rr_tp1"].append(float(risk.get("rr_tp1", risk.get("rr", 0))))
            stats["avg_rr_tp2"].append(float(risk.get("rr_tp2", 0)))
            stats["avg_rr_tp3"].append(float(risk.get("rr_tp3", 0)))
        else:
            stats["validation_fail"] += 1
            for err in v.errors:
                stats["rejection_reasons"][err[:100]] += 1
                if "Duplicate" in err:
                    stats["duplicate_tp_failures"] += 1
                if "R:R" in err:
                    stats["invalid_rr_failures"] += 1

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    report = {
        **stats,
        "rejection_reasons": dict(stats["rejection_reasons"].most_common(20)),
        "avg_risk_pct": _avg(stats["avg_risk_pct"]),
        "avg_rr_tp1": _avg(stats["avg_rr_tp1"]),
        "avg_rr_tp2": _avg(stats["avg_rr_tp2"]),
        "avg_rr_tp3": _avg(stats["avg_rr_tp3"]),
        "valid_signals": stats["validation_pass"],
    }
    for key in ("avg_risk_pct", "avg_rr_tp1", "avg_rr_tp2", "avg_rr_tp3"):
        if key in stats:
            del report[key]

    out = Path(".cache/historical_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"Report written to {out}")
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="*", default=None)
    args = parser.parse_args()
    run_validation(args.symbols)
