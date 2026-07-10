#!/usr/bin/env python3
"""Run repeated scan diagnostics and summarize (for pre/post change validation)."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DEFAULT_INTERVAL, SCANNER_SYMBOLS
from app.diagnostics.pipeline_diagnostic import diagnose_symbol, format_diagnostic_block
from app.pipeline import TradingPipeline


def main() -> None:
    cycles = int(sys.argv[1] if len(sys.argv) > 1 else 24)
    pipeline = TradingPipeline()
    records = []

    print(f"Collecting {cycles} cycles x {len(SCANNER_SYMBOLS)} symbols...")
    for cycle in range(cycles):
        for symbol in SCANNER_SYMBOLS:
            try:
                diag = diagnose_symbol(pipeline, symbol, interval=DEFAULT_INTERVAL)
                records.append(diag)
            except Exception as exc:
                print(f"ERROR {symbol} cycle {cycle}: {exc}", file=sys.stderr)

    n = len(records)
    signals = sum(1 for d in records if d.engine_signal in ("BUY", "SELL"))
    alerts = sum(1 for d in records if d.would_alert)
    confidences = [d.confidence for d in records]
    rejections = Counter(d.rejection_reason.split("|")[0].strip() for d in records)

    conf_buckets = Counter()
    for c in confidences:
        if c < 20:
            conf_buckets["0-19"] += 1
        elif c < 40:
            conf_buckets["20-39"] += 1
        elif c < 60:
            conf_buckets["40-59"] += 1
        elif c < 80:
            conf_buckets["60-79"] += 1
        else:
            conf_buckets["80-100"] += 1

    ob_pass = sum(1 for d in records if any(c.name == "Order Block" and c.passed for c in d.checks))
    fvg_pass = sum(1 for d in records if any(c.name == "FVG" and c.passed for c in d.checks))

    lines = [
        "# Multi-Cycle Diagnostic Report",
        "",
        f"- Total scans: **{n}**",
        f"- Cycles: **{cycles}**",
        f"- Symbols per cycle: **{len(SCANNER_SYMBOLS)}**",
        f"- Engine signals (BUY/SELL): **{signals}**",
        f"- Telegram-eligible: **{alerts}**",
        f"- Order Block PASS: **{ob_pass}/{n}** ({ob_pass/n*100:.0f}%)",
        f"- FVG PASS: **{fvg_pass}/{n}** ({fvg_pass/n*100:.0f}%)",
        "",
        "## Confidence distribution",
        "",
    ]
    for bucket in ("0-19", "20-39", "40-59", "60-79", "80-100"):
        lines.append(f"- {bucket}: {conf_buckets.get(bucket, 0)}")
    if confidences:
        lines.append(
            f"- min: {min(confidences):.1f} | max: {max(confidences):.1f} | "
            f"avg: {sum(confidences)/len(confidences):.1f}"
        )

    lines.extend(["", "## Top rejection reasons", ""])
    for reason, count in rejections.most_common(8):
        lines.append(f"- {reason}: {count}")

    out = Path("docs/MULTI_CYCLE_DIAGNOSTIC_REPORT.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {out}")

    sample = records[-1] if records else None
    if sample:
        print("\n--- Latest scan sample ---")
        print(format_diagnostic_block(sample))


if __name__ == "__main__":
    main()
