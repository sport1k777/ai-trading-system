"""X/Twitter intelligence — only when API credentials are configured."""

from __future__ import annotations

import logging

from app.config import INTELLIGENCE_SOCIAL_ENABLED, TWITTER_BEARER_TOKEN
from app.intelligence.models import ProviderResult
from app.intelligence.providers.base import IntelligenceProvider

logger = logging.getLogger(__name__)


class SocialTwitterProvider(IntelligenceProvider):
    name = "social_twitter"

    def is_enabled(self) -> bool:
        return INTELLIGENCE_SOCIAL_ENABLED and bool(TWITTER_BEARER_TOKEN)

    def fetch(self, symbols: list[str]) -> ProviderResult:
        if not self.is_enabled():
            return ProviderResult(
                self.name,
                False,
                error="X/Twitter data unavailable (no API credentials configured)",
            )

        # Placeholder for future X API v2 integration — never fabricate tweets.
        return ProviderResult(
            self.name,
            False,
            error="X API integration not yet implemented — credentials present but adapter pending",
        )
