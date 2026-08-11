"""Grade assignment and dynamic confidence for PRO V2."""

from __future__ import annotations

from app.analysis.pro_v2.htf_bias import HTFBias
from app.analysis.pro_v2.models import ConfirmationResult, SetupNarrative, SignalGrade
from app.config import PRO_V2_MIN_GRADE


GRADE_BASE = {"A+": 95.0, "A": 85.0, "B": 70.0, "C": 50.0}
GRADE_ORDER = {"A+": 4, "A": 3, "B": 2, "C": 1}


def assign_grade(
    narrative: SetupNarrative,
    confirmations: list[ConfirmationResult],
    htf: HTFBias,
    risk: dict | None,
) -> tuple[SignalGrade, float]:
    """Grade and confidence are derived only after a validated trade plan exists."""
    conf_hits = sum(1 for c in confirmations if c.aligned)
    step_hits = sum(1 for s in narrative.steps if s.completed)

    rr1 = float(risk.get("rr_tp1", risk.get("rr", 0))) if risk else 0.0
    rr2 = float(risk.get("rr_tp2", 0)) if risk else 0.0
    rr3 = float(risk.get("rr_tp3", 0)) if risk else 0.0

    if not risk or rr1 <= 0:
        return "C", 0.0

    if narrative.complete and conf_hits >= 3 and htf.strength >= 85 and rr1 >= 2.5 and rr3 >= 3.5:
        grade: SignalGrade = "A+"
    elif narrative.complete and conf_hits >= 2 and htf.strength >= 70 and rr1 >= 1.5:
        grade = "A"
    elif step_hits >= len(narrative.steps) - 2 and conf_hits >= 1 and rr1 >= 1.5:
        grade = "B"
    else:
        grade = "C"

    confidence = GRADE_BASE[grade]
    confidence += min(5.0, htf.strength / 20)
    confidence += min(3.0, conf_hits * 1.5)
    if rr1 >= 2.0:
        confidence += 1.0
    if rr2 >= 2.5:
        confidence += 0.5
    if rr3 >= 3.5:
        confidence += 0.5
    confidence = min(99.0, round(confidence, 1))

    return grade, confidence


def grade_emits_signal(grade: SignalGrade) -> bool:
    return GRADE_ORDER[grade] >= GRADE_ORDER.get(PRO_V2_MIN_GRADE, 3)


def direction_from_narrative(narrative: SetupNarrative) -> str | None:
    if not narrative.direction:
        return None
    return "BUY" if narrative.direction == "LONG" else "SELL"
