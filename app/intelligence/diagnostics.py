"""Structured candidate diagnostic logging for backtesting and audit."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import CANDIDATE_DIAGNOSTICS_PATH
from app.intelligence.models import CandidateDiagnostic, IntelligenceScores, SymbolIntelligence
from app.intelligence.market_regime import GlobalMarketRegime
from app.pipeline import AnalysisResult

logger = logging.getLogger(__name__)


class DiagnosticStore:
    """Append-only JSONL store for every candidate decision."""

    def __init__(self, path: str | None = None):
        self.path = Path(path or CANDIDATE_DIAGNOSTICS_PATH)

    def record(self, diagnostic: CandidateDiagnostic) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(diagnostic), default=str) + "\n")
        except OSError as exc:
            logger.warning("Failed to write candidate diagnostic: %s", exc)

    def build_from_analysis(
        self,
        result: AnalysisResult,
        *,
        stage_reached: str,
        decision: str,
        intel: Optional[SymbolIntelligence] = None,
        scores: Optional[IntelligenceScores] = None,
        regime: Optional[GlobalMarketRegime] = None,
        rejection_reasons: list[str] | None = None,
    ) -> CandidateDiagnostic:
        signal = result.signal
        risk = result.risk or {}
        direction = signal.get("signal", "WAIT")

        diag = CandidateDiagnostic(
            symbol=result.symbol,
            timestamp=datetime.now(timezone.utc).isoformat(),
            stage_reached=stage_reached,
            decision=decision if decision else (direction if direction in ("BUY", "SELL") else "WAIT"),
            technical_score=scores.technical_score if scores else float(
                signal.get("confidence", signal.get("confluence", 0))
            ),
            news_score=scores.news_score if scores else (intel.news_score if intel else None),
            social_score=scores.social_score if scores else (intel.social_score if intel else None),
            fundamental_score=scores.fundamental_score if scores else (
                intel.fundamental_score if intel else None
            ),
            onchain_score=scores.onchain_score if scores else (intel.onchain_score if intel else None),
            market_regime=regime.label if regime else "",
            liquidity_score=scores.liquidity_score if scores else 0.0,
            risk_score=scores.risk_score if scores else 0.0,
            composite_score=scores.composite_score if scores else 0.0,
            entry=_f(risk.get("entry")),
            stop=_f(risk.get("stop")),
            tp1=_f(risk.get("tp1")),
            tp2=_f(risk.get("tp2")),
            tp3=_f(risk.get("tp3")),
            rr1=_f(risk.get("rr_tp1", risk.get("rr"))),
            rr2=_f(risk.get("rr_tp2")),
            rr3=_f(risk.get("rr_tp3")),
            confidence=_f(signal.get("confidence", signal.get("confluence"))),
            rejection_reasons=list(rejection_reasons or []),
            data_sources=list(scores.sources_used if scores else (intel.available_sources if intel else [])),
            intelligence_summary=_intel_summary(intel, scores),
        )
        return diag


def _f(val) -> Optional[float]:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _intel_summary(
    intel: Optional[SymbolIntelligence],
    scores: Optional[IntelligenceScores],
) -> dict:
    out: dict = {}
    if intel:
        out["available"] = intel.available_sources
        out["unavailable"] = intel.unavailable_sources
        out["blockers"] = intel.blockers
        out["warnings"] = intel.warnings
    if scores:
        out["composite"] = scores.composite_score
        out["confidence_adjustment"] = scores.confidence_adjustment
        out["key_reasons"] = scores.key_reasons
        out["score_blockers"] = scores.blockers
    return out
