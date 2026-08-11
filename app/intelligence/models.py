"""Data models for multi-source market intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Optional


class ReliabilityTier(IntEnum):
    """Source reliability hierarchy (higher = more trustworthy)."""

    OFFICIAL = 4
    REPUTABLE = 3
    ANALYST = 2
    SOCIAL = 1
    UNKNOWN = 0


@dataclass
class IntelligenceItem:
    """Single piece of external intelligence — never fabricated."""

    source: str
    category: str  # news, social, onchain, fundamental, market
    headline: str
    summary: str = ""
    url: str = ""
    symbol: str = ""
    sentiment: float = 0.0  # -1..+1
    relevance: float = 0.0  # 0..1
    reliability: ReliabilityTier = ReliabilityTier.UNKNOWN
    published_at: Optional[datetime] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict = field(default_factory=dict)
    is_blocking: bool = False
    block_reason: str = ""

    @property
    def age_minutes(self) -> float:
        ref = self.published_at or self.fetched_at
        return max(0.0, (datetime.now(timezone.utc) - ref).total_seconds() / 60.0)


@dataclass
class ProviderResult:
    """Result from a single data provider."""

    provider: str
    available: bool
    items: list[IntelligenceItem] = field(default_factory=list)
    error: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class SymbolIntelligence:
    """Aggregated intelligence for one symbol."""

    symbol: str
    available_sources: list[str] = field(default_factory=list)
    unavailable_sources: list[str] = field(default_factory=list)
    items: list[IntelligenceItem] = field(default_factory=list)
    news_score: Optional[float] = None
    social_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    onchain_score: Optional[float] = None
    market_micro_score: Optional[float] = None
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None
    spread_pct: Optional[float] = None
    turnover_24h: Optional[float] = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def has_source(self, name: str) -> bool:
        return name in self.available_sources


@dataclass
class IntelligenceScores:
    """Structured scoring output for ranking and gating."""

    symbol: str
    technical_score: float = 0.0
    regime_score: float = 0.0
    liquidity_score: float = 0.0
    momentum_score: float = 0.0
    news_score: Optional[float] = None
    social_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    onchain_score: Optional[float] = None
    setup_quality_score: float = 0.0
    risk_score: float = 0.0
    composite_score: float = 0.0
    confidence_adjustment: float = 0.0
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    key_reasons: list[str] = field(default_factory=list)
    data_freshness_minutes: Optional[float] = None
    sources_used: list[str] = field(default_factory=list)
    sources_unavailable: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.blockers)


@dataclass
class CandidateDiagnostic:
    """Structured diagnostic record for every scanned candidate."""

    symbol: str
    timestamp: str
    stage_reached: str
    decision: str  # WAIT, BUY, SELL, REJECTED
    technical_score: float = 0.0
    news_score: Optional[float] = None
    social_score: Optional[float] = None
    fundamental_score: Optional[float] = None
    onchain_score: Optional[float] = None
    market_regime: str = ""
    liquidity_score: float = 0.0
    risk_score: float = 0.0
    composite_score: float = 0.0
    entry: Optional[float] = None
    stop: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    rr1: Optional[float] = None
    rr2: Optional[float] = None
    rr3: Optional[float] = None
    confidence: Optional[float] = None
    rejection_reasons: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    intelligence_summary: dict = field(default_factory=dict)
