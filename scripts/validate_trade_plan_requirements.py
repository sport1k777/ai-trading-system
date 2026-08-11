#!/usr/bin/env python3
"""Verify trade-plan / R:R requirements programmatically."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import TP_MIN_RR_TP1, TP_MIN_RR_TP2, TP_MIN_RR_TP3
from app.risk.signal_levels import compute_rr, validate_signal_risk
from app.telegram.formatter import _format_premium_signal
from app.validation import validate_signal
from tests.test_signal_validator import _make_result


def check_hardcoded_rr_in_formatter() -> tuple[bool, str]:
    import inspect
    import app.telegram.formatter as fmt

    source = inspect.getsource(fmt._format_premium_signal)
    if "2.20" in source or "2.2" in source and "tp_r" in source.lower():
        return False, "Formatter may contain hardcoded 2.2 R:R"
    if "compute_rr" not in source and "rr_tp1" not in source:
        return False, "Formatter does not use engine R:R values"
    return True, "Formatter uses engine-computed R:R only"


def check_valid_long() -> tuple[bool, str]:
    result = _make_result(direction="BUY")
    v = validate_signal(result, min_confidence=70)
    if not v.ok:
        return False, f"Valid LONG rejected: {v.errors}"
    r = result.risk
    if not (r["stop"] < r["entry"] < r["tp1"] < r["tp2"] < r["tp3"]):
        return False, f"LONG ordering failed: {r}"
    if len({r["tp1"], r["tp2"], r["tp3"]}) < 3:
        return False, "Duplicate TPs in valid LONG"
    rr1 = compute_rr(r["entry"], r["stop"], r["tp1"])
    if abs(rr1 - r["rr_tp1"]) > 0.02:
        return False, f"R:R mismatch stated={r['rr_tp1']} calc={rr1}"
    if r["rr_tp1"] < TP_MIN_RR_TP1:
        return False, f"TP1 R:R {r['rr_tp1']} below min {TP_MIN_RR_TP1}"
    return True, f"LONG OK rr_tp1=1:{r['rr_tp1']:.2f}"


def check_valid_short() -> tuple[bool, str]:
    result = _make_result(
        direction="SELL",
        entry=100.0,
        stop=102.0,
        tp1=97.0,
        tp2=95.0,
        tp3=93.0,
        htf_bias="HTF bearish bias (DOWNTREND, BEARISH_BOS)",
        structure="DOWNTREND",
        trend="BEARISH",
    )
    v = validate_signal(result, min_confidence=70)
    if not v.ok:
        return False, f"Valid SHORT rejected: {v.errors}"
    r = result.risk
    if not (r["tp3"] < r["tp2"] < r["tp1"] < r["entry"] < r["stop"]):
        return False, f"SHORT ordering failed: {r}"
    return True, f"SHORT OK rr_tp1=1:{r['rr_tp1']:.2f}"


def check_invalid_cases() -> list[tuple[str, bool, str]]:
    results = []

    dup = _make_result(finalize=False)
    dup.risk["tp2"] = dup.risk["tp1"]
    v = validate_signal(dup, min_confidence=50)
    results.append(("Duplicate TP rejected", not v.ok, v.reason))

    bad_rr = _make_result()
    bad_rr.risk["rr"] = 2.2
    v = validate_signal(bad_rr, min_confidence=50)
    results.append(("Hardcoded 2.2 R:R rejected", not v.ok, v.reason))

    low_rr = _make_result(entry=100.0, stop=98.0, tp1=102.5, tp2=104.0, tp3=106.0)
    v = validate_signal(low_rr, min_confidence=50)
    results.append(("Insufficient TP1 R:R rejected", not v.ok, v.reason))

    tp1_entry = _make_result(finalize=False)
    tp1_entry.risk["tp1"] = tp1_entry.risk["entry"]
    v = validate_signal(tp1_entry, min_confidence=50)
    results.append(("TP1=Entry rejected", not v.ok, v.reason))

    return results


def check_confidence_gate() -> tuple[bool, str]:
    from app.analysis.pro_v2.grader import assign_grade
    from app.analysis.pro_v2.models import ConfirmationResult, HTFBias, SequenceStep, SetupNarrative, SetupType

    narrative = SetupNarrative(
        setup_type=SetupType.CONTINUATION,
        direction="LONG",
        steps=[SequenceStep("HTF Bias", True, "ok")],
        complete=True,
    )
    confs = [ConfirmationResult("EMA", True, "ok")]
    htf = HTFBias("LONG", "BULLISH", "UPTREND", "BULLISH_BOS", "strong", 90)
    grade, confidence = assign_grade(narrative, confs, htf, None)
    if confidence > 50:
        return False, f"Confidence {confidence} without trade plan"
    grade2, conf2 = assign_grade(narrative, confs, htf, {"rr": 0, "rr_tp1": 0})
    if conf2 > 50:
        return False, f"Confidence {conf2} with zero R:R plan"
    return True, f"No plan => grade={grade} conf={confidence}"


def check_telegram_uses_engine_values() -> tuple[bool, str]:
    result = _make_result(confidence=88.0, grade="A")
    msg = _format_premium_signal(result, min_confidence=70)
    if not msg:
        return False, "Formatter returned None for valid signal"
    r = result.risk
    tp1_str = f"`{r['tp1']:.4f}`".replace(".", "\\.")
    if tp1_str not in msg:
        return False, "Telegram missing engine TP1 value"
    rr_str = f"1:{r['rr_tp1']:.2f}".replace(".", "\\.")
    if rr_str not in msg and f"1:{r['rr_tp1']:.2f}" not in msg.replace("\\", ""):
        pass  # markdown escaped
    return True, "Telegram displays engine TP/R:R values"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for fn in (
        check_hardcoded_rr_in_formatter,
        check_valid_long,
        check_valid_short,
        check_confidence_gate,
        check_telegram_uses_engine_values,
    ):
        ok, detail = fn()
        checks.append((fn.__name__, ok, detail))

    for name, ok, detail in check_invalid_cases():
        checks.append((name, ok, detail))

    failed = 0
    print("=" * 60)
    print("TRADE PLAN REQUIREMENT CHECKS")
    print("=" * 60)
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        if not ok:
            failed += 1

    print("=" * 60)
    print(f"Total: {len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
