"""Data models for Signal Engine PRO."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["LONG", "SHORT", "NEUTRAL"]


@dataclass(frozen=True)
class ConditionResult:
    name: str
    direction: Direction
    aligned: bool
    weight: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "direction": self.direction,
            "aligned": self.aligned,
            "weight": self.weight,
            "reason": self.reason,
        }


@dataclass
class ConfluenceScore:
    long_score: float
    short_score: float
    long_hits: int
    short_hits: int
    conditions: list[ConditionResult] = field(default_factory=list)
    long_reasons: list[str] = field(default_factory=list)
    short_reasons: list[str] = field(default_factory=list)

    @property
    def total_conditions(self) -> int:
        return len(self.conditions)
