"""On-chain intelligence — only when provider credentials are configured."""

from __future__ import annotations

from app.config import INTELLIGENCE_ONCHAIN_ENABLED, ONCHAIN_API_KEY
from app.intelligence.models import ProviderResult
from app.intelligence.providers.base import IntelligenceProvider


class OnChainProvider(IntelligenceProvider):
    name = "onchain"

    def is_enabled(self) -> bool:
        return INTELLIGENCE_ONCHAIN_ENABLED and bool(ONCHAIN_API_KEY)

    def fetch(self, symbols: list[str]) -> ProviderResult:
        if not self.is_enabled():
            return ProviderResult(
                self.name,
                False,
                error="On-chain data unavailable (no provider configured)",
            )
        return ProviderResult(
            self.name,
            False,
            error="On-chain provider adapter not yet implemented",
        )
