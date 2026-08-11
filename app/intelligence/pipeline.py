"""8-stage market intelligence scanning pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.config import (
    FAST_SCAN_CANDIDATE_COUNT,
    FAST_SCAN_ENABLED,
    FAST_SCAN_MIN_UNIVERSE,
    INTELLIGENCE_ENABLED,
    INTELLIGENCE_MIN_COMPOSITE_SCORE,
    SCANNER_SYMBOL_TARGET,
)
from app.intelligence.aggregator import IntelligenceAggregator
from app.intelligence.diagnostics import DiagnosticStore
from app.intelligence.market_regime import GlobalMarketRegime, MarketRegimeAnalyzer
from app.intelligence.models import SymbolIntelligence
from app.intelligence.scoring import score_candidate
from app.pipeline import AnalysisResult, TradingPipeline
from app.scanner.fast_scanner import FastScanScore, rank_symbols, score_from_df

logger = logging.getLogger(__name__)


@dataclass
class CycleStats:
    """Aggregated metrics for one intelligence scan cycle."""

    universe_count: int = 0
    cheap_filter_survivors: int = 0
    deeply_analyzed: int = 0
    buy_candidates: int = 0
    sell_candidates: int = 0
    wait_count: int = 0
    rejected_count: int = 0
    signals_sent: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)

    def record_rejection(self, reason: str) -> None:
        key = reason[:80] if reason else "unknown"
        self.rejection_reasons[key] = self.rejection_reasons.get(key, 0) + 1
        self.rejected_count += 1


@dataclass
class CycleContext:
    """Shared context for one scan cycle."""

    universe: list[str]
    candidates: list[str]
    fast_scores: dict[str, float]
    intelligence: dict[str, SymbolIntelligence]
    regime: GlobalMarketRegime
    stats: CycleStats


class IntelligencePipeline:
    """
    Stages 1–5 orchestration:
    1 Discovery (symbol universe — caller supplies)
    2 Cheap filter (fast scan)
    3 Technical analysis (delegated to TradingPipeline per symbol)
    4 Intelligence research (batch providers)
    5 AI ranking (score_candidate — applied per symbol after stage 3)
    """

    def __init__(
        self,
        pipeline: TradingPipeline,
        *,
        aggregator: Optional[IntelligenceAggregator] = None,
        diagnostics: Optional[DiagnosticStore] = None,
    ):
        self.pipeline = pipeline
        client = getattr(pipeline.collector, "client", None)
        self.aggregator = aggregator or IntelligenceAggregator(client=client)
        self.regime_analyzer = MarketRegimeAnalyzer(collector=pipeline.collector)
        self.diagnostics = diagnostics or DiagnosticStore()

    def prepare_cycle(
        self,
        universe: list[str],
        fast_scan_fn: Callable[[str], FastScanScore | object],
    ) -> CycleContext:
        stats = CycleStats(universe_count=len(universe))

        # Stage 2 — cheap filter
        if (
            FAST_SCAN_ENABLED
            and len(universe) > FAST_SCAN_MIN_UNIVERSE
        ):
            candidates = rank_symbols(
                universe,
                fast_scan_fn,
                top_n=FAST_SCAN_CANDIDATE_COUNT,
            )
            if not candidates:
                candidates = universe[:FAST_SCAN_CANDIDATE_COUNT]
        else:
            candidates = universe

        stats.cheap_filter_survivors = len(candidates)

        fast_scores: dict[str, float] = {}
        for sym in candidates:
            try:
                sc = fast_scan_fn(sym)
                if hasattr(sc, "score"):
                    fast_scores[sym] = float(sc.score)
            except Exception:
                fast_scores[sym] = 0.0

        # Stage 4 — intelligence research (batch, top candidates only)
        intelligence: dict[str, SymbolIntelligence] = {}
        if INTELLIGENCE_ENABLED and candidates:
            intelligence = self.aggregator.fetch_batch(candidates)
        else:
            intelligence = {
                s: SymbolIntelligence(symbol=s, unavailable_sources=["intelligence_disabled"])
                for s in candidates
            }

        # BTC / global regime (once per cycle)
        regime = self.regime_analyzer.analyze()

        logger.info(
            "Intelligence cycle prepared | universe=%d candidates=%d regime=%s",
            len(universe),
            len(candidates),
            regime.label,
        )

        return CycleContext(
            universe=universe,
            candidates=candidates,
            fast_scores=fast_scores,
            intelligence=intelligence,
            regime=regime,
            stats=stats,
        )

    def score_analysis(
        self,
        result: AnalysisResult,
        ctx: CycleContext,
    ) -> tuple[Optional[object], list[str]]:
        """
        Stage 5 — rank and gate candidate after technical analysis.
        Returns (IntelligenceScores | None, rejection_reasons).
        """
        ctx.stats.deeply_analyzed += 1
        direction = result.signal.get("signal", "WAIT")

        if direction not in ("BUY", "SELL"):
            ctx.stats.wait_count += 1
            return None, []

        intel = ctx.intelligence.get(
            result.symbol,
            SymbolIntelligence(symbol=result.symbol),
        )
        fast = ctx.fast_scores.get(result.symbol, 0.0)
        scores = score_candidate(result, intel, ctx.regime, fast_scan_score=fast)

        reasons: list[str] = []
        if scores.blocked:
            reasons.extend(scores.blockers)
            ctx.stats.record_rejection(scores.blockers[0])
            if direction == "BUY":
                ctx.stats.buy_candidates += 1
            else:
                ctx.stats.sell_candidates += 1
            return scores, reasons

        if scores.composite_score < INTELLIGENCE_MIN_COMPOSITE_SCORE:
            reason = (
                f"Composite intelligence score {scores.composite_score:.1f} "
                f"below minimum {INTELLIGENCE_MIN_COMPOSITE_SCORE:.1f}"
            )
            reasons.append(reason)
            ctx.stats.record_rejection(reason)

        if direction == "BUY":
            ctx.stats.buy_candidates += 1
        else:
            ctx.stats.sell_candidates += 1

        return scores, reasons

    def attach_intelligence_to_signal(
        self,
        result: AnalysisResult,
        scores,
        ctx: CycleContext,
    ) -> None:
        """Embed intelligence metadata on the signal dict for formatter/validation."""
        intel = ctx.intelligence.get(result.symbol)
        result.signal["intelligence"] = {
            "composite_score": scores.composite_score,
            "technical_score": scores.technical_score,
            "regime_score": scores.regime_score,
            "liquidity_score": scores.liquidity_score,
            "momentum_score": scores.momentum_score,
            "news_score": scores.news_score,
            "social_score": scores.social_score,
            "fundamental_score": scores.fundamental_score,
            "onchain_score": scores.onchain_score,
            "risk_score": scores.risk_score,
            "setup_quality_score": scores.setup_quality_score,
            "confidence_adjustment": scores.confidence_adjustment,
            "key_reasons": scores.key_reasons,
            "warnings": scores.warnings + (intel.warnings if intel else []),
            "blockers": scores.blockers,
            "sources_used": scores.sources_used,
            "sources_unavailable": scores.sources_unavailable,
            "market_regime": ctx.regime.label,
            "btc_trend": ctx.regime.btc_trend,
            "risk_mode": ctx.regime.risk_mode,
            "data_freshness_minutes": scores.data_freshness_minutes,
        }
        adj = scores.confidence_adjustment
        if adj and "confidence" in result.signal:
            base = float(result.signal["confidence"])
            result.signal["confidence"] = max(0.0, min(100.0, base + adj))
