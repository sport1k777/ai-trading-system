#!/usr/bin/env python3
"""Production-like scan: universe discovery, fast scan, deep analysis — no Telegram."""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SIGNAL_ENGINE_VERSION", "v2")

import logging

logging.getLogger("app").setLevel(logging.WARNING)

from app.config import FAST_SCAN_CANDIDATE_COUNT, SCANNER_SYMBOL_TARGET
from app.pipeline import TradingPipeline
from app.scanner.fast_scanner import rank_symbols, score_from_df
from app.scanner.symbol_universe import fetch_linear_usdt_universe
from app.services.signal_service import SignalService
from app.validation import validate_signal
from app.indicators.extended import ExtendedIndicators
from app.indicators.signals import SignalIndicators


def main() -> dict:
    pipeline = TradingPipeline()
    client = getattr(pipeline.collector, "client", None)

    print("=" * 60)
    print("SYMBOL UNIVERSE DISCOVERY")
    print("=" * 60)
    try:
        symbols, stats = fetch_linear_usdt_universe(client=client, target=SCANNER_SYMBOL_TARGET)
        print(f"Total instruments:     {stats.total_instruments}")
        print(f"USDT filter:           {stats.after_usdt_filter}")
        print(f"Tradable (Trading):    {stats.after_status_filter}")
        print(f"Liquid (vol/spread):   {stats.after_liquidity_filter}")
        print(f"Selected for scan:     {stats.selected}")
        print(f"Target configured:     {SCANNER_SYMBOL_TARGET}")
    except Exception as exc:
        print(f"Universe fetch FAILED: {exc}")
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
        stats = None

    print()
    print("=" * 60)
    print("STAGE 1 — FAST SCAN")
    print("=" * 60)

    def fast_fn(sym: str):
        try:
            df = pipeline.collector.get_candles(symbol=sym, interval="15", limit=80)
            if df is None or len(df) < 30:
                return score_from_df(sym, df)
            df = SignalIndicators.add_all(df)
            df = ExtendedIndicators.add_all(df)
            return score_from_df(sym, df)
        except Exception as exc:
            from app.scanner.fast_scanner import FastScanScore
            return FastScanScore(symbol=sym, score=-1.0, error=str(exc))

    t0 = time.monotonic()
    candidates = rank_symbols(symbols, fast_fn, top_n=FAST_SCAN_CANDIDATE_COUNT)
    fast_elapsed = time.monotonic() - t0
    print(f"Universe scanned:      {len(symbols)}")
    print(f"Fast scan candidates:  {len(candidates)} (top_n={FAST_SCAN_CANDIDATE_COUNT})")
    print(f"Fast scan elapsed:     {fast_elapsed:.1f}s")
    if candidates:
        print(f"Top candidates:        {', '.join(candidates[:10])}{'...' if len(candidates) > 10 else ''}")

    print()
    print("=" * 60)
    print("STAGE 2 — DEEP ANALYSIS")
    print("=" * 60)

    deep_targets = candidates or symbols[:FAST_SCAN_CANDIDATE_COUNT]
    wait = buy = sell = 0
    validation_pass = 0
    validation_fail = 0
    no_risk = 0
    rejection_reasons: Counter = Counter()

    t1 = time.monotonic()
    for sym in deep_targets:
        try:
            result = pipeline.analyze(symbol=sym, interval="15", limit=120)
        except Exception as exc:
            rejection_reasons[f"pipeline_error:{sym}"] += 1
            continue

        direction = result.signal.get("signal", "WAIT")
        if direction == "WAIT":
            wait += 1
            reason = (result.signal.get("explanation") or "unknown")[:80]
            rejection_reasons[reason] += 1
            continue
        if direction == "BUY":
            buy += 1
        elif direction == "SELL":
            sell += 1

        if not result.risk:
            no_risk += 1
            rejection_reasons["actionable_but_no_risk"] += 1
            continue

        v = validate_signal(result, min_confidence=0)
        if v.ok:
            validation_pass += 1
        else:
            validation_fail += 1
            for err in v.errors:
                rejection_reasons[err[:100]] += 1

    deep_elapsed = time.monotonic() - t1

    report = {
        "universe_discovered": len(symbols),
        "universe_target": SCANNER_SYMBOL_TARGET,
        "filter_stats": stats.__dict__ if stats else {},
        "fast_scan_count": len(symbols),
        "fast_scan_candidates": len(candidates),
        "deep_analysis_count": len(deep_targets),
        "wait": wait,
        "buy_engine": buy,
        "sell_engine": sell,
        "validation_pass": validation_pass,
        "validation_fail": validation_fail,
        "no_risk": no_risk,
        "valid_telegram_ready": validation_pass,
        "fast_scan_seconds": round(fast_elapsed, 2),
        "deep_scan_seconds": round(deep_elapsed, 2),
        "top_rejection_reasons": dict(rejection_reasons.most_common(15)),
    }

    print(f"Deep analysis targets: {len(deep_targets)}")
    print(f"Deep scan elapsed:     {deep_elapsed:.1f}s")
    print(f"WAIT:                  {wait}")
    print(f"BUY (engine):          {buy}")
    print(f"SELL (engine):         {sell}")
    print(f"No risk levels:        {no_risk}")
    print(f"Validation PASS:       {validation_pass}")
    print(f"Validation FAIL:       {validation_fail}")
    print(f"Telegram-ready signals:{validation_pass}")
    print()
    print("Top rejection reasons:")
    for reason, count in rejection_reasons.most_common(10):
        print(f"  [{count}x] {reason}")

    out = Path(".cache/production_like_scan.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print()
    print(f"Report written to {out}")
    return report


if __name__ == "__main__":
    main()
