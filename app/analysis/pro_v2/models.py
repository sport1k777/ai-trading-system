"""Data models for Signal Engine PRO V2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional

Direction = Literal["LONG", "SHORT"]
SignalGrade = Literal["A+", "A", "B", "C"]


class SetupType(str, Enum):
    CONTINUATION = "continuation"
    REVERSAL = "reversal"
    NONE = "none"


@dataclass
class GateResult:
    name: str
    passed: bool
    reason: str
    blocking: bool = True


@dataclass
class HTFBias:
    direction: Optional[Direction]
    trend: str
    structure: str
    bos: str
    reason: str
    strength: float = 0.0


@dataclass
class DealingRange:
    high: float
    low: float
    equilibrium: float
    zone: str
    reason: str


@dataclass
class SequenceStep:
    name: str
    completed: bool
    reason: str


@dataclass
class SetupNarrative:
    setup_type: SetupType
    direction: Optional[Direction]
    steps: list[SequenceStep] = field(default_factory=list)
    complete: bool = False
    summary: str = ""


@dataclass
class ConfirmationResult:
    name: str
    aligned: bool
    reason: str


@dataclass
class ProV2Signal:
    signal: str
    grade: SignalGrade
    confidence: float
    direction: Optional[Direction]
    entry: Optional[float]
    stop: Optional[float]
    tp: Optional[float]
    tp1: Optional[float]
    tp2: Optional[float]
    tp3: Optional[float]
    risk_reward: Optional[float]
    reasons: list[str]
    explanation: str
    gates_passed: list[str]
    gates_failed: list[str]
    setup_type: str = "pro_v2_signal"
    narrative: str = ""
    htf_bias: str = ""
    dealing_range_zone: str = ""
    feature_scores: list[dict] = field(default_factory=list)
    buy_confidence: float = 0.0
    sell_confidence: float = 0.0
    confluence_hits: dict = field(default_factory=dict)
    trend: str = "SIDEWAYS"
    structure: str = "RANGE"
    bos: str = "NO_BOS"
    choch: str = "NO_CHOCH"
    liquidity: Optional[dict] = None
    orderblock: Optional[dict] = None
    fvg: Optional[dict] = None
    swing_highs: list = field(default_factory=list)
    swing_lows: list = field(default_factory=list)

    def to_dict(self) -> dict:
        conf_int = int(round(self.confidence))
        direction = self.signal
        return {
            "signal": direction,
            "score": conf_int if direction == "BUY" else (-conf_int if direction == "SELL" else 0),
            "confluence": conf_int,
            "confidence": round(self.confidence, 1),
            "grade": self.grade,
            "setup_type": self.setup_type,
            "tp_price": self.tp,
            "entry": self.entry,
            "stop": self.stop,
            "tp": self.tp,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "risk_reward": self.risk_reward,
            "reasons": self.reasons,
            "explanation": self.explanation,
            "narrative": self.narrative,
            "htf_bias": self.htf_bias,
            "dealing_range_zone": self.dealing_range_zone,
            "gates_passed": self.gates_passed,
            "gates_failed": self.gates_failed,
            "feature_scores": self.feature_scores,
            "buy_confidence": self.buy_confidence,
            "sell_confidence": self.sell_confidence,
            "confluence_hits": self.confluence_hits,
            "trend": self.trend,
            "structure": self.structure,
            "bos": self.bos,
            "choch": self.choch,
            "liquidity": self.liquidity,
            "orderblock": self.orderblock,
            "fvg": self.fvg,
            "swing_highs": self.swing_highs,
            "swing_lows": self.swing_lows,
        }
