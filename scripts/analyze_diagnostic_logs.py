#!/usr/bin/env python3
"""Parse VPS diagnostic logs and summarize scan activity."""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path


def parse_blocks(text: str) -> list[dict]:
    blocks = re.split(r"(?m)^(?=[A-Z]{2,}USDT)", text)
    records: list[dict] = []
    for block in blocks:
        block = block.strip()
        if not block or "USDT" not in block.split("\n", 1)[0]:
            continue
        lines = block.splitlines()
        symbol = lines[0].strip()
        confidence = None
        decision = None
        rejection = None
        for line in lines:
            if line.startswith("Confidence score:"):
                confidence = float(line.split(":", 1)[1].strip())
            elif line.startswith("Final decision:"):
                decision = line.split(":", 1)[1].strip()
            elif line.startswith("Rejection reason:"):
                rejection = line.split(":", 1)[1].strip()
        records.append(
            {
                "symbol": symbol,
                "confidence": confidence,
                "decision": decision or "UNKNOWN",
                "rejection": rejection or "",
                "raw": block,
            }
        )
    return records


def summarize(records: list[dict]) -> str:
    n = len(records)
    signals = [r for r in records if r["decision"].startswith("ALERT")]
    confidences = [r["confidence"] for r in records if r["confidence"] is not None]
    rejections = Counter(
        (r["rejection"].split("|")[0].strip() or "unknown") for r in records if r["decision"] == "WAIT"
    )

    lines = [
        "# Diagnostic Log Summary",
        "",
        f"- Scans parsed: **{n}**",
        f"- Signals generated: **{len(signals)}**",
        "",
        "## Confidence distribution",
        "",
    ]

    if confidences:
        buckets = Counter()
        for c in confidences:
            if c < 20:
                buckets["0-19"] += 1
            elif c < 40:
                buckets["20-39"] += 1
            elif c < 60:
                buckets["40-59"] += 1
            elif c < 80:
                buckets["60-79"] += 1
            else:
                buckets["80-100"] += 1
        for bucket in ("0-19", "20-39", "40-59", "60-79", "80-100"):
            lines.append(f"- {bucket}: {buckets.get(bucket, 0)}")
        lines.append(f"- min: {min(confidences):.1f} | max: {max(confidences):.1f} | avg: {sum(confidences)/len(confidences):.1f}")
    else:
        lines.append("- No confidence values found")

    lines.extend(["", "## Top rejection reasons", ""])
    for reason, count in rejections.most_common(10):
        lines.append(f"- {reason}: {count}")

    if signals:
        lines.extend(["", "## Signals", ""])
        for r in signals:
            lines.append(f"- {r['symbol']}: {r['decision']} (confidence {r['confidence']})")

    return "\n".join(lines)


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/VPS_DIAGNOSTIC_LOGS.txt")
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    text = path.read_text(encoding="utf-8", errors="replace")
    records = parse_blocks(text)
    report = summarize(records)
    print(report)
    out = path.with_name("VPS_DIAGNOSTIC_SUMMARY.md")
    out.write_text(report, encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
