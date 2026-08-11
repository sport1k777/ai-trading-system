#!/usr/bin/env python3
"""Validate multi-source intelligence system before deployment.

SIGNAL-ONLY: no trade execution. Does not deploy anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


def run_pytest(targets: str) -> bool:
    import subprocess

    args = [sys.executable, "-m", "pytest", "-q", *targets.split()]
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    print(r.stdout or r.stderr)
    return r.returncode == 0


def main() -> int:
    section("1. Intelligence module imports")
    try:
        from app.intelligence import (
            IntelligenceAggregator,
            IntelligencePipeline,
            score_candidate,
        )
        from app.intelligence.providers import (
            BybitMarketProvider,
            FundamentalProvider,
            NewsRssProvider,
            OnChainProvider,
            SocialTwitterProvider,
        )

        print("OK — all intelligence modules import cleanly")
    except Exception as exc:
        print(f"FAIL — import error: {exc}")
        return 1

    section("2. Provider availability audit")
    providers = [
        BybitMarketProvider(),
        NewsRssProvider(),
        SocialTwitterProvider(),
        OnChainProvider(),
        FundamentalProvider(),
    ]
    for p in providers:
        status = "enabled" if p.is_enabled() else "disabled/unavailable"
        print(f"  {p.name}: {status}")

    section("3. Intelligence unit tests")
    ok = run_pytest("tests/test_intelligence.py")
    if not ok:
        return 1

    section("4. Core test suite (TP/R:R/signal-only)")
    ok = run_pytest(
        "tests/test_trade_plan_engine.py tests/test_signal_validator.py "
        "tests/test_signal_only.py tests/test_telegram_formatter.py"
    )
    if not ok:
        return 1

    section("5. Symbol universe (live Bybit — may fail from restricted regions)")
    try:
        from app.scanner.symbol_universe import get_scan_symbols
        from app.utils.bybit_client import BybitClient

        client = BybitClient()
        symbols = get_scan_symbols(client=client)
        print(f"Discovered {len(symbols)} liquid USDT perpetual symbols")
        if len(symbols) < 30:
            print("WARN — fewer than 30 symbols (Bybit API may be blocked)")
    except Exception as exc:
        print(f"SKIP — live universe: {exc}")

    section("6. Mock intelligence pipeline cycle")
    try:
        from unittest.mock import MagicMock

        from app.intelligence.pipeline import IntelligencePipeline
        from app.pipeline import TradingPipeline
        from app.scanner.fast_scanner import FastScanScore

        pipeline = TradingPipeline()
        intel = IntelligencePipeline(pipeline)

        def mock_fast(sym: str) -> FastScanScore:
            return FastScanScore(symbol=sym, score=50.0, adx=25.0)

        universe = [f"SYM{i}USDT" for i in range(120)]
        ctx = intel.prepare_cycle(universe, mock_fast)
        print(f"Universe: {ctx.stats.universe_count}")
        print(f"Cheap filter survivors: {ctx.stats.cheap_filter_survivors}")
        print(f"Intelligence fetched for: {len(ctx.intelligence)} symbols")
        print(f"BTC regime: {ctx.regime.label}")
    except Exception as exc:
        print(f"FAIL — mock cycle: {exc}")
        return 1

    section("7. Signal-only safety")
    ok = run_pytest("tests/test_signal_only.py")
    if not ok:
        return 1

    section("8. Configuration summary")
    from app import config

    cfg = {
        "INTELLIGENCE_ENABLED": config.INTELLIGENCE_ENABLED,
        "SCANNER_SYMBOL_TARGET": config.SCANNER_SYMBOL_TARGET,
        "FAST_SCAN_CANDIDATE_COUNT": config.FAST_SCAN_CANDIDATE_COUNT,
        "INTELLIGENCE_MIN_COMPOSITE_SCORE": config.INTELLIGENCE_MIN_COMPOSITE_SCORE,
        "MIN_REWARD_ATR_MULT": config.MIN_REWARD_ATR_MULT,
        "TP_MIN_RR_TP1": config.TP_MIN_RR_TP1,
    }
    print(json.dumps(cfg, indent=2))

    section("RESULT")
    print("Intelligence validation complete — DO NOT DEPLOY until live Bybit scan passes on VPS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
