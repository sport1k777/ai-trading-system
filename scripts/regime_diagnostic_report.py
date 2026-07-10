#!/usr/bin/env python3
"""24h-style regime diagnostic statistics (replay scans)."""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.market_regime import MarketRegime, estimate_win_rate
from app.config import DEFAULT_INTERVAL, SCANNER_SYMBOLS
from app.diagnostics.pipeline_diagnostic import diagnose_symbol
from app.pipeline import TradingPipeline


def _regime_from_diag(diag) -> MarketRegime:
    trend = diag.regime_trend or "range"
    vol = diag.regime_volatility or "normal"
    return MarketRegime(trend_regime=trend, volatility_regime=vol)


def main() -> None:
    cycles = int(sys.argv[1] if len(sys.argv) > 1 else 48)
    pipeline = TradingPipeline()

    regime_counts: Counter = Counter()
    signals_by_regime: Counter = Counter()
    conf_by_regime: dict[str, list[float]] = defaultdict(list)
    rejections: Counter = Counter()
    check_fails: Counter = Counter()
    win_estimates: list[float] = []

    total = 0
    signals = 0

    print(f"Regime diagnostic replay: {cycles} cycles x {len(SCANNER_SYMBOLS)} symbols")
    for _ in range(cycles):
        for symbol in SCANNER_SYMBOLS:
            try:
                diag = diagnose_symbol(pipeline, symbol, interval=DEFAULT_INTERVAL)
            except Exception as exc:
                print(f"ERROR {symbol}: {exc}", file=sys.stderr)
                continue

            total += 1
            regime_label = diag.regime or "Unknown"
            regime_counts[regime_label] += 1
            conf_by_regime[regime_label].append(diag.confidence)
            win_estimates.append(estimate_win_rate(diag.confidence, _regime_from_diag(diag)))

            if diag.engine_signal in ("BUY", "SELL"):
                signals += 1
                signals_by_regime[regime_label] += 1

            reason = diag.rejection_reason.split("|")[0].strip()
            rejections[reason] += 1
            for check in diag.failed_checks:
                check_fails[check.name] += 1

    lines = [
        "# Regime Diagnostic Statistics",
        "",
        f"- Total scans: **{total}**",
        f"- Signals generated: **{signals}**",
        f"- Avg estimated win-rate: **{sum(win_estimates)/len(win_estimates):.1%}**" if win_estimates else "",
        "",
        "## Market regime distribution",
        "",
    ]
    for label, count in regime_counts.most_common():
        pct = count / total * 100 if total else 0
        avg_conf = sum(conf_by_regime[label]) / len(conf_by_regime[label])
        lines.append(
            f"- **{label}**: {count} ({pct:.0f}%) | avg confidence {avg_conf:.1f} | "
            f"signals {signals_by_regime.get(label, 0)}"
        )

    lines.extend(["", "## Rejection reasons", ""])
    for reason, count in rejections.most_common(12):
        pct = count / total * 100 if total else 0
        lines.append(f"- {reason}: {count} ({pct:.0f}%)")

    lines.extend(["", "## Check failure breakdown", ""])
    for name, count in check_fails.most_common():
        lines.append(f"- {name}: {count}")

    report = "\n".join(lines)
    out = Path("docs/REGIME_DIAGNOSTIC_REPORT.md")
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
