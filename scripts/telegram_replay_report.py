#!/usr/bin/env python3
"""Generate final replay report from per-symbol JSON outputs."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import SCANNER_SYMBOLS

OUT_DIR = Path(".cache/replay70")
MERGED = Path(".cache/telegram_replay_70.json")
GATE = 70.0


def bucket(conf: float) -> str:
    if conf < 20:
        return "0-19"
    if conf < 40:
        return "20-39"
    if conf < 60:
        return "40-59"
    if conf < 70:
        return "60-69"
    if conf < 80:
        return "70-79"
    if conf < 90:
        return "80-89"
    return "90-100"


def main() -> int:
    errors: list[str] = []
    per_symbol: list[dict] = []
    all_engine: list[dict] = []
    all_alerts: list[dict] = []

    for sym in SCANNER_SYMBOLS:
        path = OUT_DIR / f"{sym}.json"
        if not path.exists():
            errors.append(f"Missing JSON: {path}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"Failed to read {path}: {exc}")
            continue
        engine = data.get("engine") or []
        alerts = data.get("alerts") or []
        per_symbol.append(
            {
                "symbol": sym,
                "bars_scanned": data.get("bars_scanned", 0),
                "engine_signals": data.get("engine_signals", len(engine)),
                "telegram_alerts": data.get("telegram_alerts", len(alerts)),
                "elapsed_s": data.get("elapsed_s"),
            }
        )
        all_engine.extend(engine)
        all_alerts.extend(alerts)

    conf_buckets = Counter(bucket(float(e.get("confidence", 0))) for e in all_engine)
    alert_buckets = Counter(bucket(float(a.get("confidence", 0))) for a in all_alerts)

    lines = [
        "# Telegram Threshold Replay Report (70%)",
        "",
        "## Summary",
        "",
        f"- Telegram gate: **{GATE:.0f}%**",
        f"- Replay cadence: every **4** closed bars across the 1000-bar window (replay-only; live logic unchanged)",
        f"- Symbols: {', '.join(SCANNER_SYMBOLS)}",
        f"- Total bar scans: **{sum(s['bars_scanned'] for s in per_symbol)}**",
        f"- Total engine signals (BUY/SELL): **{sum(s['engine_signals'] for s in per_symbol)}**",
        f"- Telegram alerts (>= {GATE:.0f}% + risk OK): **{len(all_alerts)}**",
        "",
        "## Signals per symbol",
        "",
        "| Symbol | Bars scanned | Engine signals | Telegram alerts @70% | Elapsed (s) |",
        "|--------|--------------|----------------|----------------------|-------------|",
    ]
    for s in per_symbol:
        lines.append(
            f"| {s['symbol']} | {s['bars_scanned']} | {s['engine_signals']} | "
            f"{s['telegram_alerts']} | {s.get('elapsed_s', '—')} |"
        )

    lines.extend(
        [
            "",
            "## Confidence distribution (all engine signals)",
            "",
        ]
    )
    for b in ("0-19", "20-39", "40-59", "60-69", "70-79", "80-89", "90-100"):
        lines.append(f"- {b}: {conf_buckets.get(b, 0)}")
    if all_engine:
        confs = [float(e["confidence"]) for e in all_engine]
        lines.append(
            f"- min: {min(confs):.1f} | max: {max(confs):.1f} | "
            f"avg: {sum(confs)/len(confs):.1f}"
        )

    lines.extend(
        [
            "",
            f"## Telegram alerts @ {GATE:.0f}% (confidence distribution)",
            "",
        ]
    )
    for b in ("70-79", "80-89", "90-100"):
        lines.append(f"- {b}: {alert_buckets.get(b, 0)}")
    lines.append(f"- **Total alerts: {len(all_alerts)}**")

    lines.extend(["", "## Example alerts", ""])
    if all_alerts:
        for a in sorted(all_alerts, key=lambda x: -float(x["confidence"]))[:10]:
            lines.append(
                f"- **{a['symbol']}** | {a['ts']} | {a['direction']} | "
                f"{float(a['confidence']):.1f}% | {a.get('reason', '')}"
            )
    else:
        lines.append("- No Telegram-eligible alerts in replay window.")

    lines.extend(["", "## Errors / notes", ""])
    if errors:
        for e in errors:
            lines.append(f"- {e}")
    else:
        lines.append("- None")

    for sym in SCANNER_SYMBOLS:
        log = OUT_DIR / f"{sym}.log"
        if log.exists() and log.stat().st_size == 0 and not (OUT_DIR / f"{sym}.json").exists():
            lines.append(f"- {sym}: worker log empty (output written only on completion)")

    report = "\n".join(lines) + "\n"
    out_path = OUT_DIR / "REPLAY_REPORT.md"
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved: {out_path}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
