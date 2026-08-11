"""Production-grade signal validation — runs before every Telegram alert."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.analysis.poi_proximity import near_zone
from app.analysis.pro_v2.grader import GRADE_BASE, GRADE_ORDER
from app.config import (
    TELEGRAM_NOTIFY_MIN_CONFIDENCE,
    TP_MIN_RR_TP1,
    TP_MIN_RR_TP2,
    TP_MIN_RR_TP3,
    VALIDATION_ENTRY_MAX_DISTANCE_PCT,
    VALIDATION_MAX_RISK_PCT,
    VALIDATION_MIN_RISK_PCT,
    VALIDATION_PRICE_DRIFT_MAX_PCT,
    VALIDATION_RR_TOLERANCE_PCT,
)
from app.pipeline import AnalysisResult
from app.risk.signal_levels import compute_rr

VALID_GRADES = frozenset(GRADE_BASE.keys())
COUNTER_TREND_SELL = "counter trend sell"
COUNTER_TREND_BUY = "counter trend buy"


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""
    errors: list[str] = field(default_factory=list)
    counter_trend: bool = False
    counter_trend_label: str = ""
    metrics: dict = field(default_factory=dict)


def _pct_distance(base: float, target: float) -> float:
    if base == 0:
        return 0.0
    return abs(target - base) / abs(base) * 100.0


def _risk_pct(entry: float, stop: float) -> float:
    return _pct_distance(entry, stop)


def _reward_pct(entry: float, tp: float) -> float:
    return _pct_distance(entry, tp)


def _has_counter_trend_label(signal: dict, direction: str) -> bool:
    needle = COUNTER_TREND_SELL if direction == "SELL" else COUNTER_TREND_BUY
    parts = [
        str(signal.get("explanation") or ""),
        str(signal.get("narrative") or ""),
        " ".join(str(r) for r in (signal.get("reasons") or [])),
        str(signal.get("htf_bias") or ""),
    ]
    blob = " ".join(parts).lower()
    return needle in blob or "counter-trend" in blob


def _entry_in_order_block(direction: str, entry: float, order_block: dict | None) -> bool:
    if not order_block:
        return False
    if direction == "BUY":
        ob = order_block.get("bullish")
    else:
        ob = order_block.get("bearish")
    if not ob:
        return False
    return near_zone(entry, float(ob["low"]), float(ob["high"]))


def _validate_entry(
    direction: str,
    entry: float | None,
    *,
    order_block: dict | None,
    market_price: float,
    max_distance_pct: float,
) -> tuple[bool, str]:
    if entry is None:
        return False, "Entry missing"
    try:
        entry_f = float(entry)
    except (TypeError, ValueError):
        return False, "Entry is not numeric"

    if entry_f <= 0:
        return False, "Entry must be > 0"

    if not _entry_in_order_block(direction, entry_f, order_block):
        return False, "Entry must be inside the detected order block"

    dist_pct = _pct_distance(market_price, entry_f)
    if dist_pct > max_distance_pct:
        return False, (
            f"Entry too far from market price ({dist_pct:.2f}% > {max_distance_pct:.2f}%)"
        )

    return True, "ok"


def _validate_stop_loss(direction: str, entry: float, stop: float | None) -> tuple[bool, str, float]:
    if stop is None:
        return False, "Stop loss missing", 0.0
    try:
        stop_f = float(stop)
    except (TypeError, ValueError):
        return False, "Stop loss is not numeric", 0.0

    if direction == "BUY" and stop_f >= entry:
        return False, "BUY stop loss must be below entry", 0.0
    if direction == "SELL" and stop_f <= entry:
        return False, "SELL stop loss must be above entry", 0.0

    risk_pct = _risk_pct(entry, stop_f)
    if risk_pct < VALIDATION_MIN_RISK_PCT:
        return False, f"Risk {risk_pct:.2f}% below minimum {VALIDATION_MIN_RISK_PCT}%", risk_pct
    if risk_pct > VALIDATION_MAX_RISK_PCT:
        return False, f"Risk {risk_pct:.2f}% above maximum {VALIDATION_MAX_RISK_PCT}%", risk_pct

    return True, "ok", risk_pct


def _validate_take_profits(
    direction: str,
    entry: float,
    stop: float,
    tp1: float | None,
    tp2: float | None,
    tp3: float | None,
) -> tuple[bool, str]:
    if tp1 is None or tp2 is None or tp3 is None:
        return False, "TP1, TP2, and TP3 must all exist"

    try:
        t1, t2, t3 = float(tp1), float(tp2), float(tp3)
    except (TypeError, ValueError):
        return False, "Take-profit levels must be numeric"

    min_step = max(abs(entry - stop) * 0.05, abs(entry) * 1e-6, 1e-8)
    levels = [t1, t2, t3]

    if any(abs(tp - entry) < min_step for tp in levels):
        return False, "A take-profit level equals entry"

    if len({round(t, 8) for t in levels}) < 3:
        return False, "Take-profit levels must be unique"

    if direction == "BUY":
        if not (entry + min_step < t1 and t1 + min_step <= t2 and t2 + min_step <= t3):
            return False, "BUY requires Entry < TP1 < TP2 < TP3"
        if stop >= entry:
            return False, "BUY stop must be below entry"
    else:
        if not (entry - min_step > t1 and t1 - min_step >= t2 and t2 - min_step >= t3):
            return False, "SELL requires Entry > TP1 > TP2 > TP3"
        if stop <= entry:
            return False, "SELL stop must be above entry"

    for i in range(len(levels) - 1):
        if abs(levels[i] - levels[i + 1]) < min_step:
            return False, "Distance between TP levels must be positive"

    return True, "ok"


def _validate_risk_reward(
    entry: float,
    stop: float,
    tp1: float,
    tp2: float,
    tp3: float,
    stated_rr: float | None,
    *,
    tolerance_pct: float,
) -> tuple[bool, str, dict]:
    risk_dist = abs(entry - stop)
    if risk_dist <= 0:
        return False, "Zero risk distance", {}

    calc_rr = compute_rr(entry, stop, tp1)
    risk_pct = _risk_pct(entry, stop)
    reward_tp1_pct = _reward_pct(entry, tp1)
    reward_tp2_pct = _reward_pct(entry, tp2)
    reward_tp3_pct = _reward_pct(entry, tp3)

    if risk_pct <= 0:
        return False, "Risk percentage must be positive", {}

    implied_rr_from_pct = reward_tp1_pct / risk_pct
    if abs(implied_rr_from_pct - calc_rr) > max(0.05, tolerance_pct / 100.0):
        return False, (
            f"Reward/risk percentage mismatch with R:R "
            f"(implied 1:{implied_rr_from_pct:.2f} vs calculated 1:{calc_rr:.2f})"
        ), {}

    if stated_rr is not None:
        stated = round(float(stated_rr), 2)
        if stated != calc_rr:
            return False, (
                f"Stated R:R 1:{stated:.2f} does not match calculated 1:{calc_rr:.2f}"
            ), {}

    # Reject impossible combinations (e.g. Risk 0.38%, Reward 0.01%, R:R 1:2.20).
    if calc_rr >= 1.0 and reward_tp1_pct < risk_pct * 0.5:
        return False, (
            f"Reward {reward_tp1_pct:.2f}% too small for calculated R:R 1:{calc_rr:.2f} "
            f"at risk {risk_pct:.2f}%"
        ), {}

    metrics = {
        "risk_pct": round(risk_pct, 4),
        "reward_tp1_pct": round(reward_tp1_pct, 4),
        "reward_tp2_pct": round(reward_tp2_pct, 4),
        "reward_tp3_pct": round(reward_tp3_pct, 4),
        "rr": calc_rr,
        "rr_tp1": calc_rr,
        "rr_tp2": compute_rr(entry, stop, tp2),
        "rr_tp3": compute_rr(entry, stop, tp3),
    }

    rr2 = metrics["rr_tp2"]
    rr3 = metrics["rr_tp3"]
    if calc_rr < TP_MIN_RR_TP1:
        return False, f"TP1 R:R 1:{calc_rr:.2f} below minimum 1:{TP_MIN_RR_TP1:.1f}", metrics
    if rr2 < TP_MIN_RR_TP2:
        return False, f"TP2 R:R 1:{rr2:.2f} below minimum 1:{TP_MIN_RR_TP2:.1f}", metrics
    if rr3 < TP_MIN_RR_TP3:
        return False, f"TP3 R:R 1:{rr3:.2f} below minimum 1:{TP_MIN_RR_TP3:.1f}", metrics

    return True, "ok", metrics


def _validate_market_structure(
    direction: str,
    signal: dict,
    result: AnalysisResult,
) -> tuple[bool, str, bool, str]:
    htf_text = (signal.get("htf_bias") or "").lower()
    htf_trend = (result.trend or "").upper()
    counter_trend = False
    label = ""

    htf_bullish = "bullish" in htf_text or htf_trend == "BULLISH"
    htf_bearish = "bearish" in htf_text or (
        "bearish" in htf_text and "bullish" not in htf_text
    )

    if direction == "SELL" and htf_bullish and not htf_bearish:
        counter_trend = True
        label = "Counter Trend Sell"
        if not _has_counter_trend_label(signal, direction):
            return (
                False,
                "HTF bullish + SELL requires explicit 'Counter Trend Sell' label",
                counter_trend,
                label,
            )

    if direction == "BUY" and htf_bearish and not htf_bullish:
        counter_trend = True
        label = "Counter Trend Buy"
        if not _has_counter_trend_label(signal, direction):
            return (
                False,
                "HTF bearish + BUY requires explicit 'Counter Trend Buy' label",
                counter_trend,
                label,
            )

    structure = (result.structure or signal.get("structure") or "").upper()
    if direction == "BUY" and structure == "DOWNTREND" and htf_bearish:
        if not _has_counter_trend_label(signal, direction):
            return (
                False,
                "Strong bearish structure + BUY requires explicit counter-trend label",
                True,
                "Counter Trend Buy",
            )

    if direction == "SELL" and structure == "UPTREND" and htf_bullish:
        if not _has_counter_trend_label(signal, direction):
            return (
                False,
                "Strong bullish structure + SELL requires explicit counter-trend label",
                True,
                "Counter Trend Sell",
            )

    return True, "ok", counter_trend, label


def _validate_confidence(
    signal: dict,
    *,
    min_confidence: float,
) -> tuple[bool, str]:
    raw = signal.get("confidence", signal.get("confluence"))
    if raw is None:
        return False, "Confidence missing"

    try:
        confidence = float(raw)
    except (TypeError, ValueError):
        return False, "Confidence is not numeric"

    if confidence < 0 or confidence > 100:
        return False, f"Confidence {confidence:.1f} outside 0-100 range"

    if confidence < min_confidence:
        return False, (
            f"Confidence {confidence:.1f} below minimum {min_confidence:.1f}"
        )

    grade = str(signal.get("grade") or "").strip()
    if grade and grade not in VALID_GRADES and grade not in ("—", "n/a", "None", ""):
        return False, f"Unknown grade {grade!r}"

    if grade in VALID_GRADES:
        floor = GRADE_BASE[grade] - 8.0
        if confidence < floor:
            return False, (
                f"Grade {grade} inconsistent with confidence {confidence:.1f} "
                f"(expected >= {floor:.1f})"
            )
        if grade == "C" and confidence >= GRADE_BASE["B"]:
            return False, f"Grade C inconsistent with confidence {confidence:.1f}"
        if grade == "B" and confidence >= GRADE_BASE["A"] + 3:
            return False, f"Grade B inconsistent with high confidence {confidence:.1f}"
        if grade == "A" and confidence >= GRADE_BASE["A+"]:
            return False, f"Grade A inconsistent with A+ confidence {confidence:.1f}"

    return True, "ok"


def _validate_price_drift(
    entry: float,
    market_price: float,
    *,
    max_drift_pct: float,
) -> tuple[bool, str]:
    drift = _pct_distance(entry, market_price)
    if drift > max_drift_pct:
        return False, (
            f"Price drift {drift:.2f}% exceeds maximum {max_drift_pct:.2f}% — "
            "entry is stale"
        )
    return True, "ok"


def _choch_required(signal: dict) -> bool:
    narrative = str(signal.get("narrative") or "").lower()
    setup = str(signal.get("setup_type") or "").lower()
    return "reversal" in narrative or setup.endswith("reversal")


def _validate_engine_context(result: AnalysisResult, direction: str) -> list[str]:
    """Verify engine context fields are present and directionally consistent."""
    signal = result.signal
    errors: list[str] = []

    liquidity = signal.get("liquidity") or result.liquidity
    if not liquidity:
        errors.append("Liquidity: no active sweep detected")
    elif direction == "BUY" and liquidity.get("type") != "SELL_SIDE_SWEEP":
        errors.append(f"Liquidity: expected SELL_SIDE_SWEEP, got {liquidity.get('type')}")
    elif direction == "SELL" and liquidity.get("type") != "BUY_SIDE_SWEEP":
        errors.append(f"Liquidity: expected BUY_SIDE_SWEEP, got {liquidity.get('type')}")

    order_block = signal.get("orderblock") or result.order_block
    if not order_block:
        errors.append("Order Block: no active order block")
    else:
        side = "bullish" if direction == "BUY" else "bearish"
        if not order_block.get(side):
            errors.append(f"Order Block: no aligned {side} zone")

    bos = signal.get("bos") or result.bos or "NO_BOS"
    if direction == "BUY" and bos != "BULLISH_BOS":
        errors.append(f"BOS: expected BULLISH_BOS, got {bos}")
    elif direction == "SELL" and bos != "BEARISH_BOS":
        errors.append(f"BOS: expected BEARISH_BOS, got {bos}")

    choch = signal.get("choch") or result.choch or "NO_CHOCH"
    if _choch_required(signal):
        if direction == "BUY" and choch != "BULLISH_CHOCH":
            errors.append(f"CHOCH: reversal requires BULLISH_CHOCH, got {choch}")
        elif direction == "SELL" and choch != "BEARISH_CHOCH":
            errors.append(f"CHOCH: reversal requires BEARISH_CHOCH, got {choch}")

    last = result.df.iloc[-1]
    close = float(last.get("close", 0))
    ema20 = float(last.get("ema20", 0))
    ema50 = float(last.get("ema50", 0))
    rsi = float(last.get("rsi", 0))
    adx = float(last.get("adx", 0))
    atr = float(last.get("atr", 0))
    volume_ratio = float(last.get("volume_ratio", 0))

    if direction == "BUY":
        if not (ema20 > ema50 and close > ema50):
            errors.append("EMA: bullish stack not confirmed")
    else:
        if not (ema20 < ema50 and close < ema50):
            errors.append("EMA: bearish stack not confirmed")

    if direction == "BUY" and not (35 <= rsi <= 75):
        errors.append(f"RSI: {rsi:.1f} outside bullish momentum range")
    if direction == "SELL" and not (25 <= rsi <= 65):
        errors.append(f"RSI: {rsi:.1f} outside bearish momentum range")

    if atr <= 0:
        errors.append("ATR: invalid or zero volatility")

    if adx <= 0:
        errors.append("ADX: invalid trend strength")

    if volume_ratio <= 0:
        errors.append("Volume: invalid volume ratio")

    return errors


def validate_signal(
    result: AnalysisResult,
    *,
    min_confidence: float | None = None,
    market_price: float | None = None,
    entry_max_distance_pct: float | None = None,
    rr_tolerance_pct: float | None = None,
    price_drift_max_pct: float | None = None,
) -> ValidationResult:
    """Validate every field before Telegram delivery. Reject if ANY rule fails."""
    min_confidence = (
        min_confidence if min_confidence is not None else TELEGRAM_NOTIFY_MIN_CONFIDENCE
    )
    entry_max_distance_pct = (
        entry_max_distance_pct
        if entry_max_distance_pct is not None
        else VALIDATION_ENTRY_MAX_DISTANCE_PCT
    )
    rr_tolerance_pct = (
        rr_tolerance_pct if rr_tolerance_pct is not None else VALIDATION_RR_TOLERANCE_PCT
    )
    price_drift_max_pct = (
        price_drift_max_pct
        if price_drift_max_pct is not None
        else VALIDATION_PRICE_DRIFT_MAX_PCT
    )

    signal = result.signal
    direction = signal.get("signal")
    errors: list[str] = []

    if direction not in ("BUY", "SELL"):
        return ValidationResult(False, "Not an actionable signal", ["Not BUY/SELL"])

    risk = result.risk
    if not risk:
        return ValidationResult(False, "Risk levels missing", ["Risk levels missing"])

    price = market_price if market_price is not None else result.price
    order_block = signal.get("orderblock") or result.order_block

    ok, msg = _validate_entry(
        direction,
        risk.get("entry"),
        order_block=order_block,
        market_price=float(price),
        max_distance_pct=entry_max_distance_pct,
    )
    if not ok:
        errors.append(f"Entry: {msg}")
        return ValidationResult(False, errors[0], errors=errors)

    entry = float(risk["entry"])
    ok, msg, risk_pct = _validate_stop_loss(direction, entry, risk.get("stop"))
    if not ok:
        errors.append(f"Stop loss: {msg}")

    stop = float(risk["stop"])
    ok, msg = _validate_take_profits(
        direction, entry, stop, risk.get("tp1"), risk.get("tp2"), risk.get("tp3")
    )
    if not ok:
        errors.append(f"Take profit: {msg}")

    tp1, tp2, tp3 = float(risk["tp1"]), float(risk["tp2"]), float(risk["tp3"])
    ok, msg, rr_metrics = _validate_risk_reward(
        entry,
        stop,
        tp1,
        tp2,
        tp3,
        risk.get("rr"),
        tolerance_pct=rr_tolerance_pct,
    )
    if not ok:
        errors.append(f"Risk/reward: {msg}")

    ok, msg, counter_trend, ct_label = _validate_market_structure(direction, signal, result)
    if not ok:
        errors.append(f"Market structure: {msg}")

    ok, msg = _validate_confidence(signal, min_confidence=min_confidence)
    if not ok:
        errors.append(f"Confidence: {msg}")

    ok, msg = _validate_price_drift(entry, float(price), max_drift_pct=price_drift_max_pct)
    if not ok:
        errors.append(f"Price drift: {msg}")

    for ctx_err in _validate_engine_context(result, direction):
        errors.append(ctx_err)

    if errors:
        return ValidationResult(
            ok=False,
            reason=errors[0],
            errors=errors,
            counter_trend=counter_trend,
            counter_trend_label=ct_label,
            metrics=rr_metrics,
        )

    metrics = {
        **rr_metrics,
        "risk_pct": round(risk_pct, 4),
        "grade": signal.get("grade"),
        "confidence": float(signal.get("confidence", signal.get("confluence", 0))),
        "grade_order": GRADE_ORDER.get(str(signal.get("grade")), 0),
    }
    return ValidationResult(
        ok=True,
        reason="ok",
        counter_trend=counter_trend,
        counter_trend_label=ct_label,
        metrics=metrics,
    )
