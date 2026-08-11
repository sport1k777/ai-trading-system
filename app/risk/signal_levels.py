"""Finalize and validate entry/stop/TP levels for Telegram alerts."""

from __future__ import annotations

from typing import Optional

from app.config import TP_MIN_RR_TP1, TP_MIN_RR_TP2, TP_MIN_RR_TP3


def compute_rr(entry: float, stop: float, tp: float) -> float:
    """Reward-to-risk ratio for a single take-profit level."""
    risk_dist = abs(entry - stop)
    if risk_dist <= 0:
        return 0.0
    return round(abs(tp - entry) / risk_dist, 2)


def _min_step(entry: float, risk_dist: float) -> float:
    return max(risk_dist * 0.1, abs(entry) * 1e-6, 1e-8)


def _tp_valid(direction: str, entry: float, tp: float, *, min_step: float) -> bool:
    if direction == "BUY":
        return tp > entry + min_step
    return tp < entry - min_step


def _ordered(direction: str, entry: float, stop: float, tps: list[float], *, min_step: float) -> bool:
    if direction == "BUY":
        return (
            stop < entry
            and _tp_valid(direction, entry, tps[0], min_step=min_step)
            and tps[0] + min_step <= tps[1]
            and tps[1] + min_step <= tps[2]
        )
    return (
        stop > entry
        and _tp_valid(direction, entry, tps[0], min_step=min_step)
        and tps[0] - min_step >= tps[1]
        and tps[1] - min_step >= tps[2]
    )


def _r_multiple_tp(direction: str, entry: float, risk_dist: float, mult: float) -> float:
    if direction == "BUY":
        return entry + mult * risk_dist
    return entry - mult * risk_dist


def finalize_take_profits(
    direction: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: Optional[float] = None,
    tp3: Optional[float] = None,
    *,
    primary_tp: Optional[float] = None,
) -> tuple[float, float, float]:
    """Recalculate TP1/TP2/TP3 after entry and stop are finalized.

    Ensures strictly distinct targets on the correct side of entry.
    """
    if direction not in ("BUY", "SELL"):
        raise ValueError(f"Invalid direction: {direction}")

    entry = round(float(entry), 2)
    stop = round(float(stop), 2)
    risk_dist = abs(entry - stop)
    if risk_dist <= 0:
        raise ValueError("Entry and stop must differ")

    min_step = _min_step(entry, risk_dist)
    candidates = [tp1, tp2, tp3, primary_tp]
    ladder: list[float] = []

    for raw in candidates:
        if raw is None:
            continue
        tp = round(float(raw), 2)
        if not _tp_valid(direction, entry, tp, min_step=min_step):
            continue
        if any(abs(tp - existing) < min_step for existing in ladder):
            continue
        ladder.append(tp)

    if not ladder:
        ladder.append(round(_r_multiple_tp(direction, entry, risk_dist, 1.0), 2))

    ladder.sort(reverse=(direction == "SELL"))

    mult = abs(ladder[-1] - entry) / risk_dist
    while len(ladder) < 3:
        mult = max(mult + 0.25, TP_MIN_RR_TP1 if len(ladder) == 0 else TP_MIN_RR_TP2 if len(ladder) == 1 else TP_MIN_RR_TP3)
        candidate = round(_r_multiple_tp(direction, entry, risk_dist, mult), 2)
        if _tp_valid(direction, entry, candidate, min_step=min_step) and all(
            abs(candidate - existing) >= min_step for existing in ladder
        ):
            ladder.append(candidate)
            ladder.sort(reverse=(direction == "SELL"))

    tp1_f, tp2_f, tp3_f = ladder[0], ladder[1], ladder[2]
    if not _ordered(direction, entry, stop, [tp1_f, tp2_f, tp3_f], min_step=min_step):
        tp1_f = round(_r_multiple_tp(direction, entry, risk_dist, TP_MIN_RR_TP1), 2)
        tp2_f = round(_r_multiple_tp(direction, entry, risk_dist, TP_MIN_RR_TP2), 2)
        tp3_f = round(_r_multiple_tp(direction, entry, risk_dist, TP_MIN_RR_TP3), 2)

    return tp1_f, tp2_f, tp3_f


def finalize_risk_levels(
    direction: str,
    entry: float,
    stop: float,
    tp1: float,
    tp2: Optional[float] = None,
    tp3: Optional[float] = None,
    *,
    primary_tp: Optional[float] = None,
) -> dict:
    """Build a validated risk dict with consistent R:R based on TP1."""
    entry = round(float(entry), 2)
    stop = round(float(stop), 2)
    tp1_f, tp2_f, tp3_f = finalize_take_profits(
        direction,
        entry,
        stop,
        tp1,
        tp2,
        tp3,
        primary_tp=primary_tp,
    )
    risk_dist = round(abs(entry - stop), 4)
    rr = compute_rr(entry, stop, tp1_f)
    return {
        "entry": entry,
        "stop": stop,
        "tp1": tp1_f,
        "tp2": tp2_f,
        "tp3": tp3_f,
        "tp": tp1_f,
        "risk": risk_dist,
        "rr": rr,
        "rr_tp1": rr,
        "rr_tp2": compute_rr(entry, stop, tp2_f),
        "rr_tp3": compute_rr(entry, stop, tp3_f),
    }


def sync_risk_rr(risk: dict) -> dict:
    """Recompute displayed R:R from finalized prices — never trust hardcoded values."""
    entry = float(risk["entry"])
    stop = float(risk["stop"])
    tp1 = float(risk["tp1"])
    tp2 = float(risk["tp2"])
    tp3 = float(risk["tp3"])
    synced = dict(risk)
    synced["rr"] = compute_rr(entry, stop, tp1)
    synced["rr_tp1"] = synced["rr"]
    synced["rr_tp2"] = compute_rr(entry, stop, tp2)
    synced["rr_tp3"] = compute_rr(entry, stop, tp3)
    return synced


def validate_signal_risk(direction: str, risk: dict, *, rr_tolerance: float = 0.02) -> tuple[bool, str]:
    """Validate trade levels before sending a Telegram alert."""
    if direction not in ("BUY", "SELL"):
        return False, f"Invalid direction: {direction}"

    required = ("entry", "stop", "tp1", "tp2", "tp3", "rr")
    for key in required:
        if risk.get(key) is None:
            return False, f"Missing {key}"

    try:
        entry = float(risk["entry"])
        stop = float(risk["stop"])
        tp1 = float(risk["tp1"])
        tp2 = float(risk["tp2"])
        tp3 = float(risk["tp3"])
        stated_rr = float(risk["rr"])
    except (TypeError, ValueError):
        return False, "Non-numeric risk level"

    risk_dist = abs(entry - stop)
    if risk_dist <= 0:
        return False, "Zero risk distance"

    min_step = _min_step(entry, risk_dist)
    reward = abs(tp1 - entry)
    if reward < min_step:
        return False, "TP1 equals entry"

    if len({round(tp1, 2), round(tp2, 2), round(tp3, 2)}) < 3:
        return False, "Duplicate take-profit levels"

    if not _ordered(direction, entry, stop, [tp1, tp2, tp3], min_step=min_step):
        return False, "Invalid level ordering for direction"

    expected_rr = compute_rr(entry, stop, tp1)
    if abs(expected_rr - round(stated_rr, 2)) > rr_tolerance:
        return False, f"R:R mismatch (stated 1:{stated_rr:.2f}, calculated 1:{expected_rr:.2f})"

    rr2 = compute_rr(entry, stop, tp2)
    rr3 = compute_rr(entry, stop, tp3)
    if expected_rr < TP_MIN_RR_TP1:
        return False, f"TP1 R:R 1:{expected_rr:.2f} below minimum 1:{TP_MIN_RR_TP1:.1f}"
    if rr2 < TP_MIN_RR_TP2:
        return False, f"TP2 R:R 1:{rr2:.2f} below minimum 1:{TP_MIN_RR_TP2:.1f}"
    if rr3 < TP_MIN_RR_TP3:
        return False, f"TP3 R:R 1:{rr3:.2f} below minimum 1:{TP_MIN_RR_TP3:.1f}"

    return True, "ok"


def normalize_risk_dict(direction: str, risk: dict) -> Optional[dict]:
    """Validate risk levels from engine output; return None when invalid.

    Does not invent TP2/TP3 — invalid plans are rejected, not patched.
    """
    required = ("entry", "stop", "tp1", "tp2", "tp3")
    if not all(risk.get(k) is not None for k in required):
        return None

    try:
        entry = float(risk["entry"])
        stop = float(risk["stop"])
        tp1 = float(risk["tp1"])
        tp2 = float(risk["tp2"])
        tp3 = float(risk["tp3"])
    except (TypeError, ValueError):
        return None

    finalized = {
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "tp1": round(tp1, 2),
        "tp2": round(tp2, 2),
        "tp3": round(tp3, 2),
        "tp": round(tp1, 2),
        "risk": round(abs(entry - stop), 4),
        "rr": compute_rr(entry, stop, tp1),
        "rr_tp1": compute_rr(entry, stop, tp1),
        "rr_tp2": compute_rr(entry, stop, tp2),
        "rr_tp3": compute_rr(entry, stop, tp3),
        "entry_type": risk.get("entry_type", "market"),
        "current_price": risk.get("current_price"),
        "entry_distance_pct": risk.get("entry_distance_pct"),
        "risk_pct": risk.get("risk_pct"),
        "reward_tp1_pct": risk.get("reward_tp1_pct"),
        "reward_tp2_pct": risk.get("reward_tp2_pct"),
        "reward_tp3_pct": risk.get("reward_tp3_pct"),
    }

    ok, _ = validate_signal_risk(direction, finalized)
    return sync_risk_rr(finalized) if ok else None
