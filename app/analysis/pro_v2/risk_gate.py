"""Pre-signal risk validation."""

from __future__ import annotations

from app.analysis.pro_v2.models import GateResult
from app.config import TP_MIN_RR_TP1, TP_MIN_RR_TP2, TP_MIN_RR_TP3


def check_risk_levels(levels: dict | None) -> GateResult:
    if not levels:
        return GateResult("Risk Levels", False, "Could not compute risk levels", blocking=True)

    rr1 = float(levels.get("rr_tp1", levels.get("rr", 0)))
    rr2 = float(levels.get("rr_tp2", 0))
    rr3 = float(levels.get("rr_tp3", 0))

    if rr1 < TP_MIN_RR_TP1:
        return GateResult(
            "Risk/Reward",
            False,
            f"TP1 R:R 1:{rr1:.2f} below minimum 1:{TP_MIN_RR_TP1:.1f}",
            blocking=True,
        )
    if rr2 < TP_MIN_RR_TP2:
        return GateResult(
            "Risk/Reward",
            False,
            f"TP2 R:R 1:{rr2:.2f} below minimum 1:{TP_MIN_RR_TP2:.1f}",
            blocking=True,
        )
    if rr3 < TP_MIN_RR_TP3:
        return GateResult(
            "Risk/Reward",
            False,
            f"TP3 R:R 1:{rr3:.2f} below minimum 1:{TP_MIN_RR_TP3:.1f}",
            blocking=True,
        )

    reason = f"TP1 1:{rr1:.2f} · TP2 1:{rr2:.2f} · TP3 1:{rr3:.2f}"
    return GateResult("Risk/Reward", True, reason, blocking=True)
