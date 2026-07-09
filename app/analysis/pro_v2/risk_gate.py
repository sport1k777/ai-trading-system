"""Pre-signal risk validation."""

from __future__ import annotations

from app.analysis.pro_v2.models import GateResult
from app.config import PRO_V2_MIN_RR


def check_risk_levels(levels: dict | None) -> GateResult:
    if not levels:
        return GateResult("Risk Levels", False, "Could not compute risk levels", blocking=True)
    rr = levels.get("rr", 0)
    passed = rr >= PRO_V2_MIN_RR
    reason = f"R:R 1:{rr:.2f} (min {PRO_V2_MIN_RR})" if passed else (
        f"R:R 1:{rr:.2f} below minimum {PRO_V2_MIN_RR}"
    )
    return GateResult("Risk/Reward", passed, reason, blocking=True)
