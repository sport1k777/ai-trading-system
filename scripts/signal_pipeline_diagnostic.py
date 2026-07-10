#!/usr/bin/env python3
"""Run a one-shot signal pipeline diagnostic across all scanner symbols."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import (
    DEFAULT_INTERVAL,
    SCANNER_SYMBOLS,
    SIGNAL_ENGINE_VERSION,
    TELEGRAM_NOTIFY_MIN_CONFIDENCE,
)
from app.diagnostics.pipeline_diagnostic import diagnose_symbol, summarize_diagnostics
from app.pipeline import TradingPipeline
from app.utils.logging_config import setup_logging


def main() -> None:
    setup_logging("scripts.signal_pipeline_diagnostic")
    interval = DEFAULT_INTERVAL
    pipeline = TradingPipeline()

    print(f"Running pipeline diagnostic | engine={SIGNAL_ENGINE_VERSION} | tf={interval}m")
    print(f"Telegram min confidence: {TELEGRAM_NOTIFY_MIN_CONFIDENCE}")
    print(f"Symbols: {', '.join(SCANNER_SYMBOLS)}\n")

    diagnostics = []
    for symbol in SCANNER_SYMBOLS:
        try:
            diag = diagnose_symbol(pipeline, symbol, interval=interval)
            diagnostics.append(diag)
        except Exception as exc:
            print(f"ERROR scanning {symbol}: {exc}", file=sys.stderr)

    report = summarize_diagnostics(diagnostics)
    print(report)

    out_path = Path("docs/SIGNAL_PIPELINE_DIAGNOSTIC.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to {out_path}")


if __name__ == "__main__":
    main()
