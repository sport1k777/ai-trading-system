#!/usr/bin/env python3
"""Fast Telegram-threshold replay on the last 1000 closed 15m bars per symbol."""
from __future__ import annotations

import json
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import logging

logging.getLogger("app").setLevel(logging.WARNING)

import pandas as pd

from app.analysis.market_context import MarketContextBuilder
from app.analysis.signal_generator import SignalGenerator
from app.collectors.candles import CandleCollector
from app.config import DEFAULT_INTERVAL, SCANNER_SYMBOLS, TELEGRAM_NOTIFY_MIN_CONFIDENCE
from app.indicators.extended import ExtendedIndicators
from app.indicators.signals import SignalIndicators
from app.pipeline import _risk_from_signal
from app.risk.risk_manager import RiskManager

WARMUP = 200
LIMIT = 1000
CACHE = Path(".cache/longterm")
OUT_DIR = Path(".cache/replay70")
# Replay-only cadence: evaluate every Nth closed bar (does not change live signal logic).
REPLAY_BAR_STEP = 4
CONTEXT_WINDOW = 260


def load_symbol_df(symbol: str) -> pd.DataFrame:
    path = CACHE / f"{symbol}_{DEFAULT_INTERVAL}m.csv"
    if path.exists():
        df = pd.read_csv(path, parse_dates=["timestamp"])
        return df.tail(LIMIT).reset_index(drop=True)
    collector = CandleCollector()
    return collector.get_candles(symbol=symbol, interval=DEFAULT_INTERVAL, limit=LIMIT)


def replay_symbol(symbol: str, gate: float) -> dict:
    """Walk-forward replay using precomputed indicators (same signal path as live)."""
    raw = load_symbol_df(symbol)
    if len(raw) < WARMUP + 10:
        raise ValueError(f"{symbol}: insufficient bars ({len(raw)})")

    prepared = ExtendedIndicators.calculate(SignalIndicators.calculate(raw))
    htf_full = MarketContextBuilder.resample_htf(prepared, bars_per_htf=4)
    if len(htf_full) >= 30:
        htf_full = SignalIndicators.calculate(htf_full)
    else:
        htf_full = pd.DataFrame()

    engine: list[dict] = []
    alerts: list[dict] = []
    bars_scanned = len(range(WARMUP, len(prepared), REPLAY_BAR_STEP))
    bars_per_htf = 4

    for i in range(WARMUP, len(prepared), REPLAY_BAR_STEP):
        start = max(0, i + 1 - CONTEXT_WINDOW)
        slice_df = prepared.iloc[start : i + 1]
        htf_df = None
        if len(htf_full) >= 30:
            htf_end = max(0, (i + 1) // bars_per_htf)
            if htf_end >= 30:
                htf_df = htf_full.iloc[:htf_end]
        ctx = MarketContextBuilder.build(
            slice_df,
            symbol=symbol,
            interval=DEFAULT_INTERVAL,
            indicators_calculated=True,
            extended_calculated=True,
            copy_closed_bars=False,
            htf_df=htf_df,
        )
        signal = SignalGenerator.generate(
            slice_df,
            indicators_calculated=True,
            context=ctx,
            symbol=symbol,
            interval=DEFAULT_INTERVAL,
        )
        direction = signal.get("signal")
        if direction not in ("BUY", "SELL"):
            continue

        confidence = float(signal.get("confidence", signal.get("confluence", 0)))
        reason = (signal.get("reasons") or ["Engine confluence passed"])[0]
        entry = {
            "symbol": symbol,
            "ts": str(prepared.iloc[i]["timestamp"]),
            "direction": direction,
            "confidence": confidence,
            "reason": reason,
        }
        engine.append(entry)

        risk = _risk_from_signal(signal)
        if risk is None:
            swing_lows = signal.get("swing_lows") or ctx.swing_lows
            swing_highs = signal.get("swing_highs") or ctx.swing_highs
            sl = swing_lows[-1]["price"] if swing_lows else None
            sh = swing_highs[-1]["price"] if swing_highs else None
            risk = RiskManager.calculate(ctx.price, ctx.atr, direction, swing_low=sl, swing_high=sh)

        if confidence >= gate and risk:
            alerts.append(entry)

    return {
        "symbol": symbol,
        "bars_scanned": bars_scanned,
        "engine_signals": len(engine),
        "telegram_alerts": len(alerts),
        "engine": engine,
        "alerts": alerts,
    }


def _replay_worker(args: tuple[str, float]) -> dict:
    symbol, gate = args
    t0 = time.time()
    result = replay_symbol(symbol, gate)
    result["elapsed_s"] = round(time.time() - t0, 1)
    return result


def write_symbol_result(result: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{result['symbol']}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return path


def merge_results(gate: float) -> dict:
    results = []
    for sym in SCANNER_SYMBOLS:
        path = OUT_DIR / f"{sym}.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing replay output: {path}")
        results.append(json.loads(path.read_text(encoding="utf-8")))

    all_alerts = [a for r in results for a in r.get("alerts", [])]
    summary = {
        "telegram_gate": gate,
        "symbols": SCANNER_SYMBOLS,
        "bar_scans": sum(r["bars_scanned"] for r in results),
        "engine_signals": sum(r["engine_signals"] for r in results),
        "telegram_alerts": sum(r["telegram_alerts"] for r in results),
        "elapsed_s": sum(r.get("elapsed_s", 0) for r in results),
        "alerts": all_alerts,
        "per_symbol": [
            {
                "symbol": r["symbol"],
                "engine_signals": r["engine_signals"],
                "telegram_alerts": r["telegram_alerts"],
                "elapsed_s": r.get("elapsed_s"),
            }
            for r in results
        ],
    }
    merged = Path(".cache/telegram_replay_70.json")
    merged.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run_report() -> str:
    import subprocess

    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "telegram_replay_report.py")],
        cwd=ROOT,
        check=True,
    )
    return (OUT_DIR / "REPLAY_REPORT.md").read_text(encoding="utf-8")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", help="Replay one symbol")
    parser.add_argument("--merge", action="store_true", help="Merge per-symbol JSON outputs")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Replay all symbols in parallel, merge, and write report",
    )
    args = parser.parse_args()

    gate = TELEGRAM_NOTIFY_MIN_CONFIDENCE

    if args.all:
        t0 = time.time()
        jobs = [(sym, gate) for sym in SCANNER_SYMBOLS]
        with ProcessPoolExecutor(max_workers=len(SCANNER_SYMBOLS)) as pool:
            futures = {pool.submit(_replay_worker, job): job[0] for job in jobs}
            for fut in as_completed(futures):
                sym = futures[fut]
                result = fut.result()
                path = write_symbol_result(result)
                print(
                    f"{sym}: engine={result['engine_signals']} "
                    f"alerts={result['telegram_alerts']} "
                    f"elapsed={result['elapsed_s']}s -> {path}"
                )
        summary = merge_results(gate)
        report = run_report()
        elapsed = round(time.time() - t0, 1)
        print(f"\nTotal elapsed: {elapsed}s")
        print(f"Telegram gate: {gate:.0f}%")
        print(f"Bar scans: {summary['bar_scans']}")
        print(f"Engine signals: {summary['engine_signals']}")
        print(f"Telegram alerts: {summary['telegram_alerts']}")
        print(f"Report: {OUT_DIR / 'REPLAY_REPORT.md'}")
        print("\n" + report)
        return 0

    if args.symbol:
        t0 = time.time()
        result = replay_symbol(args.symbol, gate)
        result["elapsed_s"] = round(time.time() - t0, 1)
        path = write_symbol_result(result)
        print(
            f"{args.symbol}: scans={result['bars_scanned']} "
            f"engine={result['engine_signals']} alerts={result['telegram_alerts']} "
            f"elapsed={result['elapsed_s']}s"
        )
        for a in result["alerts"]:
            print(
                f"  {a['symbol']} | {a['ts']} | {a['direction']} | "
                f"{a['confidence']:.1f}% | {a['reason']}"
            )
        print(f"Saved: {path}")
        return 0

    if args.merge:
        summary = merge_results(gate)
        print(json.dumps(summary, indent=2))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
