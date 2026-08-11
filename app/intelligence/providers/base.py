"""Intelligence data provider interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.intelligence.models import ProviderResult


class IntelligenceProvider(ABC):
    """Base class for modular intelligence sources."""

    name: str = "base"

    @abstractmethod
    def is_enabled(self) -> bool:
        ...

    @abstractmethod
    def fetch(self, symbols: list[str]) -> ProviderResult:
        """Fetch intelligence for symbols. Must never fabricate data."""
        ...

    def fetch_one(self, symbol: str) -> ProviderResult:
        return self.fetch([symbol])
