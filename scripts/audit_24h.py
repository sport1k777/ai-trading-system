#!/usr/bin/env python3
"""Walk-forward 24h gate audit + counterfactual threshold analysis (replay only)."""
from __future__ import annotations

import json
import logging
import sys
import warnings
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.getLogger("app").setLevel(logging.WARNING)

import pandas as pd

from app.analysis.market_context import MarketContextBuilder
from app.analysis.market_regime import (
    build_regime_profile,
    detect_regime_from_context,
    validate_regime_confirmations,
)
from app.analysis.pro.confluence import pick_direction, score_confluence
from app.analysis.signal_generator import SignalGenerator
from app.collectors.candles import CandleCollector
from app.config import (
    DEFAULT_INTERVAL,
    PRO_MIN_CONDITIONS,
    PRO_MIN_CONFIDENCE,
    PRO_MIN_DIRECTION_GAP,
    PRO_V2_HTF_INTERVAL,
    SCANNER_SYMBOLS,
    SIGNAL_ENGINE_VERSION,
    TELEGRAM_NOTIFY_MIN_CONFIDENCE,
)
from app.diagnostics.pipeline_diagnostic import (
    _build_engine_gate_checks_v1,
    diagnose_scan,
)
from app.indicators.extended import ExtendedIndicators
from app.indicators.signals import SignalIndicators
from app.pipeline import AnalysisResult, _risk_from_signal

WARMUP = 200
BARS_24H = 96  # 24 hours of 15m closes
CONTEXT_WINDOW = 260
CACHE = Path(".cache/longterm")
OUT_JSON = Path(".cache/audit_24h.json")
OUT_MD = Path("docs/AUDIT_24H_REPORT.md")


@dataclass
class ScanRecord:
    symbol: str
    ts: str
    engine_signal: str
    engine_reason: str
    candidate: str
    confidence: float
    grade: str
    buy_score: float
    sell_score: float
    long_hits: int
    short_hits: int
    regime: str
    would_alert: bool
    failed_checks: list[str] = field(default_factory=list)
    engine_gate_fails: list[str] = field(default_factory=list)
    pick_direction: str | None = None
    pick_confidence: float = 0.0
    regime_would_pass: bool = False
    regime_block_reason: str = ""


def load_symbol_df(symbol: str, *, limit: int = 400) -> pd.DataFrame:
    path = CACHE / f"{symbol}_{DEFAULT_INTERVAL}m.csv"
    if path.exists():
        df = pd.read_csv(path, parse_dates=["timestamp"])
        return df.tail(limit).reset_index(drop=True)
    collector = CandleCollector()
    return collector.get_candles(symbol=symbol, interval=DEFAULT_INTERVAL, limit=limit)


def _htf_slice(htf_full: pd.DataFrame, ltf_end: int, bars_per_htf: int = 4) -> pd.DataFrame | None:
    if len(htf_full) < 30:
        return None
    htf_end = max(0, (ltf_end + 1) // bars_per_htf)
    if htf_end < 30:
        return None
    return htf_full.iloc[:htf_end]


def replay_symbol(symbol: str, *, bars_24h: int = BARS_24H) -> list[ScanRecord]:
    raw = load_symbol_df(symbol)
    if len(raw) < WARMUP + bars_24h:
        raise ValueError(f"{symbol}: need {WARMUP + bars_24h} bars, got {len(raw)}")

    prepared = ExtendedIndicators.calculate(SignalIndicators.calculate(raw))
    htf_full = MarketContextBuilder.resample_htf(prepared, bars_per_htf=4)
    if len(htf_full) >= 30:
        htf_full = SignalIndicators.calculate(htf_full)
    else:
        htf_full = pd.DataFrame()

    start = len(prepared) - bars_24h
    records: list[ScanRecord] = []

    for i in range(start, len(prepared)):
        slice_start = max(0, i + 1 - CONTEXT_WINDOW)
        slice_df = prepared.iloc[slice_start : i + 1]
        htf_df = _htf_slice(htf_full, i)

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
            htf_df=htf_df,
        )
        result = AnalysisResult(
            symbol=symbol,
            df=ctx.df,
            signal=signal,
            risk=_risk_from_signal(signal),
            trend=ctx.trend,
            structure=ctx.structure,
            bos=ctx.bos,
            choch=ctx.choch,
            liquidity=ctx.liquidity,
            order_block=ctx.order_block,
            fvg=ctx.fvg,
            swing_highs=signal.get("swing_highs") or ctx.swing_highs,
            swing_lows=signal.get("swing_lows") or ctx.swing_lows,
        )
        diag = diagnose_scan(
            result,
            timeframe=DEFAULT_INTERVAL,
            min_confidence=TELEGRAM_NOTIFY_MIN_CONFIDENCE,
            htf_df=htf_df,
        )
        engine_gates = _build_engine_gate_checks_v1(
            result,
            ctx,
            diag,
            min_confidence=TELEGRAM_NOTIFY_MIN_CONFIDENCE,
        )
        regime = ctx.regime or detect_regime_from_context(ctx)
        profile = build_regime_profile(regime)
        confluence = score_confluence(
            last=ctx.last,
            trend=ctx.trend,
            bos=ctx.bos,
            choch=ctx.choch,
            liquidity=ctx.liquidity,
            order_block=ctx.order_block,
            fvg=ctx.fvg,
            htf_trend=ctx.htf_trend,
            structure=ctx.structure,
            regime=regime,
            profile=profile,
        )
        picked, pick_conf, _ = pick_direction(
            confluence,
            min_conditions=PRO_MIN_CONDITIONS,
            min_confidence=PRO_MIN_CONFIDENCE,
            min_gap=PRO_MIN_DIRECTION_GAP,
        )
        regime_ok, regime_reason = (
            validate_regime_confirmations(
                regime,
                picked or diag.candidate_direction,
                confluence.conditions,
                trend=ctx.trend,
                htf_trend=ctx.htf_trend,
                bos=ctx.bos,
                choch=ctx.choch,
            )
            if picked
            else (False, "No direction picked")
        )
        hits = signal.get("confluence_hits") or {}
        records.append(
            ScanRecord(
                symbol=symbol,
                ts=str(prepared.iloc[i]["timestamp"]),
                engine_signal=diag.engine_signal,
                engine_reason=(signal.get("reasons") or ["Unknown"])[0],
                candidate=diag.candidate_direction,
                confidence=diag.confidence,
                grade=diag.grade,
                buy_score=float(signal.get("buy_confidence", 0)),
                sell_score=float(signal.get("sell_confidence", 0)),
                long_hits=int(hits.get("long", 0)),
                short_hits=int(hits.get("short", 0)),
                regime=diag.regime or "Unknown",
                would_alert=diag.would_alert,
                failed_checks=[c.name for c in diag.failed_checks],
                engine_gate_fails=[c.name for c in engine_gates if not c.passed],
                pick_direction=picked,
                pick_confidence=float(pick_conf or 0),
                regime_would_pass=regime_ok,
                regime_block_reason=regime_reason if picked and not regime_ok else "",
            )
        )
    return records


def _best_side(rec: ScanRecord) -> tuple[str, float, int, int]:
    if rec.buy_score >= rec.sell_score:
        return "BUY", rec.buy_score, rec.long_hits, rec.short_hits
    return "SELL", rec.sell_score, rec.long_hits, rec.short_hits


def counterfactual_alerts(
    records: list[ScanRecord],
    *,
    min_conditions: int,
    min_confidence: float,
    min_gap: float,
    telegram_gate: float,
) -> int:
    count = 0
    for rec in records:
        from app.analysis.pro.models import ConfluenceScore

        conf = ConfluenceScore(
            long_score=rec.buy_score,
            short_score=rec.sell_score,
            long_hits=rec.long_hits,
            short_hits=rec.short_hits,
            conditions=[],
            long_reasons=[],
            short_reasons=[],
        )
        direction, confidence, _ = pick_direction(
            conf,
            min_conditions=min_conditions,
            min_confidence=min_confidence,
            min_gap=min_gap,
        )
        if direction is None or confidence < telegram_gate:
            continue
        count += 1
    return count


CHECK_NAMES = (
    "Trend", "HTF", "BOS", "CHOCH", "Liquidity", "Order Block", "FVG",
    "EMA", "ADX", "RSI", "Volume", "ATR", "Regime",
)


def aggregate(records: list[ScanRecord]) -> dict:
    total = len(records)
    gate_pass = Counter()
    gate_fail = Counter()
    engine_signals = Counter()
    rejections = Counter()
    near_miss = Counter()
    conf_buckets = Counter()
    grade_counts = Counter()
    regime_blocks = Counter()
    pick_would_pass = 0

    for rec in records:
        engine_signals[rec.engine_signal] += 1
        grade_counts[rec.grade] += 1
        side, score, lh, sh = _best_side(rec)
        hits = lh if side == "BUY" else sh
        gap = abs(rec.buy_score - rec.sell_score)

        if rec.pick_direction:
            pick_would_pass += 1
            if not rec.regime_would_pass:
                regime_blocks[rec.regime_block_reason or "Regime gate failed"] += 1

        if rec.engine_signal == "WAIT":
            if hits >= PRO_MIN_CONDITIONS and score >= PRO_MIN_CONFIDENCE and gap < PRO_MIN_DIRECTION_GAP:
                near_miss["gap_shortfall"] += 1
            elif hits >= PRO_MIN_CONDITIONS and score >= 60 and score < PRO_MIN_CONFIDENCE:
                near_miss["confidence_shortfall_60_64"] += 1
            elif hits == PRO_MIN_CONDITIONS - 1 and score >= PRO_MIN_CONFIDENCE:
                near_miss["one_condition_short"] += 1
            elif score >= PRO_MIN_CONFIDENCE and hits >= 4:
                near_miss["four_plus_hits_high_score"] += 1
            if rec.pick_direction and not rec.regime_would_pass:
                near_miss["confluence_pass_regime_block"] += 1

        if score >= 70:
            conf_buckets["70+"] += 1
        elif score >= 65:
            conf_buckets["65-69"] += 1
        elif score >= 60:
            conf_buckets["60-64"] += 1
        else:
            conf_buckets["<60"] += 1

        rejections[rec.engine_reason.split("(")[0].strip()[:80]] += 1
        failed_set = set(rec.failed_checks)
        for name in CHECK_NAMES:
            if name in failed_set:
                gate_fail[name] += 1
            else:
                gate_pass[name] += 1

    cf_grid = []
    for cond in (4, 5):
        for conf in (60, 62, 65):
            for gap in (6, 8, 10):
                alerts = counterfactual_alerts(
                    records,
                    min_conditions=cond,
                    min_confidence=conf,
                    min_gap=gap,
                    telegram_gate=TELEGRAM_NOTIFY_MIN_CONFIDENCE,
                )
                cf_grid.append(
                    {
                        "min_conditions": cond,
                        "min_confidence": conf,
                        "min_gap": gap,
                        "telegram_alerts": alerts,
                    }
                )

    return {
        "total_scans": total,
        "symbols": sorted({r.symbol for r in records}),
        "engine_signals": dict(engine_signals),
        "would_alert": sum(1 for r in records if r.would_alert),
        "pick_direction_passes": pick_would_pass,
        "regime_blocks_after_pick": dict(regime_blocks),
        "gate_fail_rates": {
            name: {"pass": gate_pass[name], "fail": gate_fail[name]}
            for name in CHECK_NAMES
        },
        "near_miss": dict(near_miss),
        "confidence_buckets_best_side": dict(conf_buckets),
        "grade_distribution": dict(grade_counts),
        "top_rejection_reasons": rejections.most_common(10),
        "counterfactual_grid": cf_grid,
        "current_thresholds": {
            "PRO_MIN_CONDITIONS": PRO_MIN_CONDITIONS,
            "PRO_MIN_CONFIDENCE": PRO_MIN_CONFIDENCE,
            "PRO_MIN_DIRECTION_GAP": PRO_MIN_DIRECTION_GAP,
            "TELEGRAM_NOTIFY_MIN_CONFIDENCE": TELEGRAM_NOTIFY_MIN_CONFIDENCE,
        },
    }


def recommend(summary: dict) -> list[str]:
    lines: list[str] = []
    total = summary["total_scans"]
    engine = summary["engine_signals"]
    engine_total = engine.get("BUY", 0) + engine.get("SELL", 0)
    alerts_now = summary["would_alert"]

    lines.append(
        f"Current 24h bar-close replay: **{total}** scans, engine BUY/SELL **{engine_total}**, "
        f"Telegram alerts **{alerts_now}** (threshold {TELEGRAM_NOTIFY_MIN_CONFIDENCE:.0f}%)."
    )

    if alerts_now > 5:
        lines.append(
            "The engine already emits more than the 2–5/day target on closed-bar replay; "
            "prefer **tightening delivery filters** (Telegram gate, per-symbol cooldown) "
            "rather than lowering PRO confluence thresholds."
        )
    elif alerts_now < 2:
        lines.append(
            "Sub-threshold confluence is the bottleneck; inspect near-miss counts before "
            "lowering PRO_MIN_CONDITIONS / PRO_MIN_CONFIDENCE."
        )

    nm = summary["near_miss"]
    if nm:
        lines.append("Near-miss breakdown (engine WAIT but close to thresholds):")
        for key, count in sorted(nm.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            lines.append(f"- **{key}**: {count} ({pct:.1f}% of scans)")

    rb = summary.get("regime_blocks_after_pick", {})
    if rb:
        lines.append("Regime blocks after confluence pick (current thresholds):")
        for reason, count in sorted(rb.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"- **{reason}**: {count}")

    grid = summary["counterfactual_grid"]
    in_band = [g for g in grid if 2 <= g["telegram_alerts"] <= 5]
    if in_band:
        best = min(
            in_band,
            key=lambda g: (
                abs(g["telegram_alerts"] - 3.5),
                g["min_conditions"],
                -g["min_confidence"],
                g["min_gap"],
            ),
        )
        lines.append(
            "Counterfactual confluence grid (Telegram gate fixed) — combo in 2–5 alerts band:"
        )
        lines.append(
            f"- `PRO_MIN_CONDITIONS={best['min_conditions']}`, "
            f"`PRO_MIN_CONFIDENCE={best['min_confidence']}`, "
            f"`PRO_MIN_DIRECTION_GAP={best['min_gap']}` → **{best['telegram_alerts']}** alerts"
        )
    elif engine_total > 5:
        lines.append(
            "Counterfactual grid did not reduce below current alert count because all "
            f"{alerts_now} alerts already meet the strictest grid point; use Telegram/cooldown tuning."
        )

    fails = summary["gate_fail_rates"]
    top_fails = sorted(fails.items(), key=lambda x: x[1]["fail"], reverse=True)[:5]
    lines.append("Top setup-filter failure rates (diagnostic checklist, candidate direction):")
    for name, stats in top_fails:
        pct = stats["fail"] / total * 100 if total else 0
        lines.append(f"- **{name}**: FAIL {stats['fail']}/{total} ({pct:.0f}%)")

    return lines


def write_report(records: list[ScanRecord], summary: dict) -> str:
    lines = [
        "# 24-Hour Gate Audit Report",
        "",
        f"- Engine: **{SIGNAL_ENGINE_VERSION}**",
        f"- Window: **{BARS_24H}** closed 15m bars per symbol (~24h)",
        f"- Symbols: **{', '.join(summary['symbols'])}**",
        f"- Total scans: **{summary['total_scans']}**",
        "",
        "## Engine outcomes",
        "",
        f"- BUY: **{summary['engine_signals'].get('BUY', 0)}**",
        f"- SELL: **{summary['engine_signals'].get('SELL', 0)}**",
        f"- WAIT: **{summary['engine_signals'].get('WAIT', 0)}**",
        f"- Telegram-eligible (current): **{summary['would_alert']}**",
        "",
        "## Gate failure rates",
        "",
        "| Gate | PASS | FAIL | FAIL % |",
        "|------|------|------|--------|",
    ]
    total = summary["total_scans"]
    for name, stats in sorted(summary["gate_fail_rates"].items()):
        fail_pct = stats["fail"] / total * 100 if total else 0
        lines.append(
            f"| {name} | {stats['pass']} | {stats['fail']} | {fail_pct:.0f}% |"
        )

    lines.extend(["", "## Regime blocks after confluence pick", ""])
    for reason, count in sorted(
        summary.get("regime_blocks_after_pick", {}).items(),
        key=lambda x: -x[1],
    )[:8]:
        lines.append(f"- **{reason}**: {count}")
    lines.append(
        f"- Confluence pick passed: **{summary.get('pick_direction_passes', 0)}** scans"
    )

    lines.extend(["", "## Near-miss analysis", ""])
    for key, count in sorted(summary["near_miss"].items(), key=lambda x: -x[1]):
        lines.append(f"- **{key}**: {count}")

    lines.extend(["", "## Confidence distribution (best side)", ""])
    for bucket, count in sorted(summary["confidence_buckets_best_side"].items()):
        lines.append(f"- **{bucket}**: {count}")

    lines.extend(["", "## Counterfactual threshold grid (Telegram gate fixed)", ""])
    lines.append("| conditions | confidence | gap | alerts/24h |")
    lines.append("|------------|------------|-----|------------|")
    for row in summary["counterfactual_grid"]:
        lines.append(
            f"| {row['min_conditions']} | {row['min_confidence']} | "
            f"{row['min_gap']} | {row['telegram_alerts']} |"
        )

    lines.extend(["", "## Recommendations (data-driven)", ""])
    lines.extend(recommend(summary))

    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=int, default=BARS_24H, help="Closed bars per symbol")
    parser.add_argument("--symbol", help="Run one symbol only")
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else SCANNER_SYMBOLS
    all_records: list[ScanRecord] = []

    for sym in symbols:
        print(f"Replaying {sym} ({args.bars} bars)...", flush=True)
        recs = replay_symbol(sym, bars_24h=args.bars)
        all_records.extend(recs)
        eng = sum(1 for r in recs if r.engine_signal in ("BUY", "SELL"))
        alert = sum(1 for r in recs if r.would_alert)
        print(f"  {sym}: scans={len(recs)} engine={eng} alerts={alert}")

    summary = aggregate(all_records)
    summary["records_sample"] = [asdict(r) for r in all_records[:5]]

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {"summary": summary, "records": [asdict(r) for r in all_records]},
            indent=2,
        ),
        encoding="utf-8",
    )

    report = write_report(all_records, summary)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"\nWrote {OUT_JSON} and {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
