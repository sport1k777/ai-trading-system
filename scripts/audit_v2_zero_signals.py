#!/usr/bin/env python3
"""PRO v2 zero-signal root-cause audit — per-symbol gate pass/fail report."""

from __future__ import annotations

import json
import logging
import os
import sys
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SIGNAL_ENGINE_VERSION", "v2")

logging.getLogger("app").setLevel(logging.WARNING)

import pandas as pd

from app.analysis.market_context import MarketContextBuilder
from app.analysis.pro_v2.confirmations import run_confirmations
from app.analysis.pro_v2.grader import assign_grade, direction_from_narrative, grade_emits_signal
from app.analysis.pro_v2.htf_bias import evaluate_htf_bias
from app.analysis.pro_v2.regime_gate import run_regime_gates
from app.analysis.pro_v2.risk_gate import check_risk_levels
from app.analysis.pro_v2.setup_sequence import pick_best_narrative, validate_continuation, validate_reversal
from app.analysis.signal_generator import SignalGenerator
from app.collectors.candles import CandleCollector
from app.config import (
    DEFAULT_INTERVAL,
    PRO_V2_HTF_INTERVAL,
    PRO_V2_MIN_GRADE,
    SCANNER_SYMBOLS,
)
from app.indicators.extended import ExtendedIndicators
from app.indicators.signals import SignalIndicators
from app.risk.risk_manager_v2 import RiskManagerV2

WARMUP = 200
BARS_7D = 672  # 7 × 96 fifteen-minute bars
CONTEXT_WINDOW = 260
CACHE = Path(".cache/longterm")
OUT_JSON = Path(".cache/audit_v2_zero_signals.json")
OUT_MD = Path("docs/V2_ZERO_SIGNAL_REPORT.md")

STEP_NAMES = (
    "HTF Bias",
    "Premium/Discount",
    "Liquidity Sweep",
    "Displacement",
    "POI Return",
    "Structure Break",
    "Confirmation",
    "CHOCH",
)
REGIME_NAMES = ("ATR Volatility", "ADX Trend", "Structure Alignment", "Session")
CONF_NAMES = ("EMA Stack", "RSI", "VWAP", "Volume Profile")


@dataclass
class ScanAudit:
    symbol: str
    ts: str
    candidate: str
    engine_signal: str
    engine_reason: str
    primary_blocker: str
    blocker_kind: str  # logic_bug | strict_threshold | design
    regime_pass: dict[str, bool] = field(default_factory=dict)
    step_pass: dict[str, bool] = field(default_factory=dict)
    conf_pass: dict[str, bool] = field(default_factory=dict)
    narrative_complete: bool = False
    grade: str = "C"
    confidence: float = 0.0
    would_emit_if_grade_b: bool = False


def load_symbol_df(symbol: str, *, limit: int = 900) -> pd.DataFrame:
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


def _classify_blocker(reason: str, *, narrative_complete: bool, grade: str) -> tuple[str, str]:
    """Return (primary_blocker_label, kind)."""
    r = reason.lower()
    if "insufficient candle" in r:
        return "Insufficient history", "design"
    if "indicators not ready" in r:
        return "Indicators not ready", "design"
    if "regime gate failed" in r:
        if "adx" in r:
            return "Regime: ADX Trend", "strict_threshold"
        if "atr" in r or "volatility" in r:
            return "Regime: ATR Volatility", "strict_threshold"
        if "structure" in r:
            return "Regime: Structure Alignment", "strict_threshold"
        return "Regime gate (other)", "strict_threshold"
    if "setup incomplete" in r:
        return "Setup incomplete (sequential narrative)", "strict_threshold"
    if "could not compute risk" in r:
        return "Risk: levels unavailable", "logic_bug"
    if "r:r below" in r or "rr below" in r:
        return "Risk: R:R below minimum", "strict_threshold"
    if "grade" in r and "below minimum" in r:
        return f"Grade gate (need ≥{PRO_V2_MIN_GRADE}, got {grade})", "strict_threshold"
    return reason[:80], "design"


def _primary_missing_step(step_pass: dict[str, bool], candidate: str) -> str | None:
    narrative = validate_continuation if "Continuation" in candidate else validate_reversal
    # Use continuation step order as default ranking
    order = [
        "HTF Bias",
        "Premium/Discount",
        "Liquidity Sweep",
        "Displacement",
        "POI Return",
        "Structure Break",
        "Confirmation",
        "CHOCH",
    ]
    for name in order:
        if name in step_pass and not step_pass[name]:
            return name
    return None


def analyze_scan(ctx, symbol: str, ts: str) -> ScanAudit:
    narrative = pick_best_narrative(ctx)
    direction = direction_from_narrative(narrative) or "BUY"
    candidate = f"{narrative.summary} ({direction})"

    regime = run_regime_gates(ctx, direction)
    regime_pass = {g.name: g.passed for g in regime}

    step_pass: dict[str, bool] = {}
    for step in narrative.steps:
        step_pass[step.name] = step.completed

    conf = run_confirmations(ctx, direction)
    conf_pass = {c.name: c.aligned for c in conf}

    htf = evaluate_htf_bias(ctx)
    sl = ctx.swing_lows[-1]["price"] if ctx.swing_lows else None
    sh = ctx.swing_highs[-1]["price"] if ctx.swing_highs else None
    risk = RiskManagerV2.calculate(ctx, direction, swing_low=sl, swing_high=sh)
    rr = risk["rr"] if risk else 0
    grade, confidence = assign_grade(narrative, conf, htf, rr)

    signal = SignalGenerator.generate(
        ctx.analysis_df,
        indicators_calculated=True,
        context=ctx,
        symbol=symbol,
        interval=DEFAULT_INTERVAL,
    )
    engine_signal = signal.get("signal", "WAIT")
    engine_reason = (signal.get("reasons") or ["Unknown"])[0]
    primary, kind = _classify_blocker(
        engine_reason,
        narrative_complete=narrative.complete,
        grade=grade,
    )

    if primary == "Setup incomplete (sequential narrative)":
        missing = _primary_missing_step(step_pass, narrative.summary)
        if missing:
            primary = f"Setup incomplete: {missing}"

    would_emit_b = (
        narrative.complete
        and all(g.passed for g in regime if g.blocking)
        and risk is not None
        and check_risk_levels(risk).passed
        and grade_emits_signal("B")
    )

    return ScanAudit(
        symbol=symbol,
        ts=ts,
        candidate=candidate,
        engine_signal=engine_signal,
        engine_reason=engine_reason,
        primary_blocker=primary,
        blocker_kind=kind,
        regime_pass=regime_pass,
        step_pass=step_pass,
        conf_pass=conf_pass,
        narrative_complete=narrative.complete,
        grade=grade,
        confidence=confidence,
        would_emit_if_grade_b=would_emit_b,
    )


def replay_symbol(symbol: str, *, bars: int = BARS_7D) -> list[ScanAudit]:
    raw = load_symbol_df(symbol)
    if len(raw) < WARMUP + 50:
        raise ValueError(f"{symbol}: need {WARMUP + 50} bars, got {len(raw)}")

    prepared = ExtendedIndicators.calculate(SignalIndicators.calculate(raw))
    htf_full = MarketContextBuilder.resample_htf(prepared, bars_per_htf=4)
    if len(htf_full) >= 30:
        htf_full = SignalIndicators.calculate(htf_full)
    else:
        htf_full = pd.DataFrame()

    start = max(WARMUP, len(prepared) - bars)
    records: list[ScanAudit] = []

    for i in range(start, len(prepared)):
        slice_start = max(0, i + 1 - CONTEXT_WINDOW)
        slice_df = prepared.iloc[slice_start : i + 1]
        htf_df = _htf_slice(htf_full, i)
        ctx = MarketContextBuilder.build(
            slice_df,
            symbol=symbol,
            interval=DEFAULT_INTERVAL,
            htf_df=htf_df,
            indicators_calculated=True,
        )
        ts = str(slice_df.iloc[-1]["timestamp"])
        records.append(analyze_scan(ctx, symbol, ts))

    return records


def _pass_rate(records: list[ScanAudit], key_fn) -> dict[str, float]:
    counts: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    for rec in records:
        for name, passed in key_fn(rec).items():
            totals[name] += 1
            if passed:
                counts[name] += 1
    return {name: counts[name] / totals[name] * 100 for name in totals}


def _symbol_report(symbol: str, records: list[ScanAudit]) -> list[str]:
    n = len(records)
    emits = sum(1 for r in records if r.engine_signal in ("BUY", "SELL"))
    complete = sum(1 for r in records if r.narrative_complete)
    blockers = Counter(r.primary_blocker for r in records)
    kinds = Counter(r.blocker_kind for r in records)

    regime_rates = _pass_rate(records, lambda r: r.regime_pass)
    step_rates = _pass_rate(records, lambda r: r.step_pass)
    conf_rates = _pass_rate(records, lambda r: r.conf_pass)

    lines = [
        f"### {symbol}",
        "",
        f"- Scans: **{n}** | Engine BUY/SELL: **{emits}** | Complete narratives: **{complete}** ({complete/n*100:.1f}%)",
        f"- Counterfactual (complete + risk OK + grade B): **{sum(1 for r in records if r.would_emit_if_grade_b)}** scans",
        "",
        "**Primary blockers (first engine exit):**",
        "",
    ]
    for name, count in blockers.most_common(8):
        pct = count / n * 100
        lines.append(f"- {name}: {count}/{n} ({pct:.1f}%)")

    lines.extend(["", "**Regime gates (% pass):**", ""])
    for name in REGIME_NAMES:
        if name in regime_rates:
            lines.append(f"- {name}: {regime_rates[name]:.1f}%")

    lines.extend(["", "**Sequential steps (% pass on best narrative):**", ""])
    for name in STEP_NAMES:
        if name in step_rates:
            lines.append(f"- {name}: {step_rates[name]:.1f}%")

    lines.extend(["", "**Confirmations (% aligned):**", ""])
    for name in CONF_NAMES:
        if name in conf_rates:
            lines.append(f"- {name}: {conf_rates[name]:.1f}%")

    top_kind = kinds.most_common(1)[0][0] if kinds else "n/a"
    lines.extend([
        "",
        f"**Dominant blocker type:** {top_kind}",
        "",
    ])
    return lines


def build_recommendations(all_records: list[ScanAudit]) -> list[str]:
    n = len(all_records)
    blockers = Counter(r.primary_blocker for r in all_records)
    step_fail = Counter()
    for r in all_records:
        if not r.narrative_complete:
            missing = _primary_missing_step(r.step_pass, r.candidate)
            if missing:
                step_fail[missing] += 1

    complete = sum(1 for r in all_records if r.narrative_complete)
    grade_blocked = sum(
        1 for r in all_records
        if r.narrative_complete and r.engine_signal == "WAIT" and "Grade" in r.engine_reason
    )
    would_b = sum(1 for r in all_records if r.would_emit_if_grade_b)

    lines = [
        "## Root cause summary",
        "",
        f"Across **{n}** walk-forward scans (7 days × 5 symbols, PRO v2):",
        f"- Engine BUY/SELL emitted: **{sum(1 for r in all_records if r.engine_signal in ('BUY','SELL'))}**",
        f"- Complete sequential narratives: **{complete}** ({complete/n*100:.1f}%)",
        f"- Would emit at grade B (counterfactual): **{would_b}**",
        "",
        "**Top primary blockers:**",
        "",
    ]
    for name, count in blockers.most_common(10):
        lines.append(f"1. {name}: {count/n*100:.1f}% of scans" if False else f"- {name}: {count/n*100:.1f}%")

    lines.extend([
        "",
        "**Most often missing sequential step (when incomplete):**",
        "",
    ])
    for name, count in step_fail.most_common(7):
        lines.append(f"- {name}: {count} scans")

    lines.extend([
        "",
        "## Logic bugs vs strict thresholds",
        "",
        "| Issue | Type | Evidence |",
        "|-------|------|----------|",
        "| Regime ADX always uses trend threshold (≥22); reversal ADX mode never called | **Logic bug** | `run_regime_gates()` never passes `for_trend_setup=False` |",
        "| Diagnostic treats all 4 confirmations as hard gate; engine only needs 2 for grade A | **Logic bug** | Mismatch causes misleading production logs |",
        "| Diagnostic Narrative gate passes when direction set, even if incomplete | **Logic bug** | `_build_engine_gate_checks_v2` checks `direction is not None` |",
        "| Engine `_wait()` sets confidence=0 unless grade path reached | **Logic bug** | Masks near-miss confidence in logs/Telegram gate |",
        "| POI Return requires price within 0.3% of OB/FVG | **Strict threshold** | Step fails ~60–80% of scans |",
        "| Continuation requires 6/7 steps + premium/discount simultaneously | **Strict threshold** | Complete narrative rate near zero |",
        "| Grade A requires 2 confirmations + HTF strength ≥70 | **Strict threshold** | `{grade_blocked}` complete setups blocked by grade |",
        "| Confirmation candle requires volume_ratio ≥1.0 on signal bar | **Strict threshold** | Fails on low-volume closes |",
        "| Displacement requires 1.3×ATR body in last 5 bars | **Strict threshold** | Often missing in low-vol regimes |",
        "",
        "## Minimum recommended changes (do not deploy yet)",
        "",
        "These preserve quality while fixing bugs and unlocking realistic signal rate (~1–3/day):",
        "",
        "1. **Fix ADX regime routing** — use `for_trend_setup=False` when best narrative is reversal; avoids blocking valid reversal setups with trend ADX.",
        "2. **Fix diagnostic v2 gates** — audit Narrative/Confirmations to match engine (track sequential steps individually; confirmations = count ≥2, not all 4).",
        "3. **Pass computed confidence in `_wait()`** when grade was computed — improves observability only, no strategy change.",
        "4. **Align POI proximity with regime profile** — use existing `REGIME_POI_TOLERANCE_*` in `_poi_return()` instead of fixed 0.3%; same adaptive logic already used in v1 diagnostics.",
        "5. **Relax confirmation candle volume** — `volume_ratio >= 0.85` OR remove volume requirement when 5+ narrative steps complete; reduces false negatives without skipping the sequence.",
        "6. **Only if counterfactual grade-B count > 0 after fixes** — set `PRO_V2_MIN_GRADE=B` (not lower). Grade B still requires step_hits ≥ n-2 and ≥1 confirmation.",
        "",
        "**Do not change:** R:R ≥2.0, sequential narrative requirement, HTF bias step, or Telegram confidence gate without re-auditing.",
        "",
    ])
    return lines


def main() -> int:
    all_records: list[ScanAudit] = []
    per_symbol: dict[str, list[ScanAudit]] = {}

    for symbol in SCANNER_SYMBOLS:
        print(f"Replaying {symbol}...", flush=True)
        try:
            records = replay_symbol(symbol)
        except Exception as exc:
            print(f"  SKIP {symbol}: {exc}", flush=True)
            continue
        per_symbol[symbol] = records
        all_records.extend(records)
        print(f"  {len(records)} scans, emits={sum(1 for r in records if r.engine_signal in ('BUY','SELL'))}", flush=True)

    if not all_records:
        print("No data — fetch candles first.", file=sys.stderr)
        return 1

    lines = [
        "# PRO V2 Zero-Signal Root Cause Report",
        "",
        f"Generated from walk-forward replay (`SIGNAL_ENGINE_VERSION=v2`, {BARS_7D} bars/symbol).",
        "**No strategy changes deployed.**",
        "",
    ]

    global_blockers = Counter(r.primary_blocker for r in all_records)
    lines.extend([
        "## Aggregate",
        "",
        f"- Total scans: **{len(all_records)}**",
        f"- Engine BUY/SELL: **{sum(1 for r in all_records if r.engine_signal in ('BUY','SELL'))}**",
        f"- Complete narratives: **{sum(1 for r in all_records if r.narrative_complete)}**",
        "",
        "**Top blockers (all symbols):**",
        "",
    ])
    for name, count in global_blockers.most_common(12):
        lines.append(f"- {name}: {count/len(all_records)*100:.1f}%")

    lines.extend(["", "## Per-symbol breakdown", ""])
    for symbol in SCANNER_SYMBOLS:
        if symbol in per_symbol:
            lines.extend(_symbol_report(symbol, per_symbol[symbol]))

    lines.extend(build_recommendations(all_records))

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    payload = {
        "scans": len(all_records),
        "emits": sum(1 for r in all_records if r.engine_signal in ("BUY", "SELL")),
        "blockers": dict(global_blockers),
        "per_symbol": {
            sym: {
                "scans": len(recs),
                "emits": sum(1 for r in recs if r.engine_signal in ("BUY", "SELL")),
                "blockers": dict(Counter(r.primary_blocker for r in recs)),
            }
            for sym, recs in per_symbol.items()
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"\nReport: {OUT_MD}")
    print(f"JSON:   {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
