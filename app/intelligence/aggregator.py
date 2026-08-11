"""Batch intelligence aggregation with caching and failure isolation."""

from __future__ import annotations

import logging
import time
from typing import Optional

from app.config import INTELLIGENCE_CACHE_SECONDS, INTELLIGENCE_ENABLED
from app.intelligence.freshness import freshness_weight
from app.intelligence.models import ProviderResult, SymbolIntelligence
from app.intelligence.providers.base import IntelligenceProvider
from app.intelligence.providers.bybit_market import BybitMarketProvider
from app.intelligence.providers.fundamental import FundamentalProvider
from app.intelligence.providers.news_rss import NewsRssProvider
from app.intelligence.providers.onchain import OnChainProvider
from app.intelligence.providers.social_twitter import SocialTwitterProvider
from app.intelligence.reliability import weighted_sentiment
from app.utils.bybit_client import BybitClient

logger = logging.getLogger(__name__)


class IntelligenceAggregator:
    """Fetch and merge intelligence from all enabled providers."""

    def __init__(
        self,
        providers: Optional[list[IntelligenceProvider]] = None,
        client: Optional[BybitClient] = None,
    ):
        self.providers = providers or [
            BybitMarketProvider(client=client),
            NewsRssProvider(),
            SocialTwitterProvider(),
            OnChainProvider(),
            FundamentalProvider(),
        ]
        self._cache: dict[str, tuple[float, dict[str, SymbolIntelligence]]] = {}

    def fetch_batch(self, symbols: list[str], *, force_refresh: bool = False) -> dict[str, SymbolIntelligence]:
        if not INTELLIGENCE_ENABLED:
            return {s: SymbolIntelligence(symbol=s, unavailable_sources=["all_disabled"]) for s in symbols}

        cache_key = ",".join(sorted(symbols[:5])) + f":{len(symbols)}"
        now = time.time()
        if not force_refresh and cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < INTELLIGENCE_CACHE_SECONDS:
                return data

        results: dict[str, SymbolIntelligence] = {s: SymbolIntelligence(symbol=s) for s in symbols}

        for provider in self.providers:
            try:
                pr = provider.fetch(symbols)
                self._merge_provider(results, pr)
            except Exception as exc:
                logger.warning("Provider %s crashed: %s", getattr(provider, "name", "?"), exc)
                for sym in symbols:
                    results[sym].unavailable_sources.append(f"{getattr(provider, 'name', '?')}:crash")

        for sym, intel in results.items():
            self._finalize_scores(intel)

        self._cache[cache_key] = (now, results)
        return results

    def _merge_provider(self, results: dict[str, SymbolIntelligence], pr: ProviderResult) -> None:
        if pr.available:
            for sym in results:
                results[sym].available_sources.append(pr.provider)
        else:
            for sym in results:
                results[sym].unavailable_sources.append(f"{pr.provider}:{pr.error or 'unavailable'}")
            if pr.provider == "bybit_market" and pr.metadata:
                for sym, meta in pr.metadata.items():
                    if sym not in results:
                        continue
                    intel = results[sym]
                    intel.spread_pct = meta.get("spread_pct")
                    intel.funding_rate = meta.get("funding_rate")
                    intel.open_interest = meta.get("open_interest")
                    intel.turnover_24h = meta.get("turnover_24h")
            return

        if pr.provider == "bybit_market" and pr.metadata:
            for sym, meta in pr.metadata.items():
                if sym in results:
                    intel = results[sym]
                    intel.spread_pct = meta.get("spread_pct")
                    intel.funding_rate = meta.get("funding_rate")
                    intel.open_interest = meta.get("open_interest")
                    intel.turnover_24h = meta.get("turnover_24h")

        for item in pr.items:
            sym = item.symbol
            if sym not in results:
                continue
            intel = results[sym]
            intel.items.append(item)
            if item.is_blocking and item.block_reason:
                intel.blockers.append(item.block_reason)

    def _finalize_scores(self, intel: SymbolIntelligence) -> None:
        by_cat: dict[str, list] = {"news": [], "social": [], "fundamental": [], "onchain": [], "market": []}
        for item in intel.items:
            by_cat.setdefault(item.category, []).append(item)

        for cat, key in [
            ("news", "news_score"),
            ("social", "social_score"),
            ("fundamental", "fundamental_score"),
            ("onchain", "onchain_score"),
            ("market", "market_micro_score"),
        ]:
            cat_items = by_cat.get(cat) or []
            if not cat_items:
                setattr(intel, key, None)
                continue
            weights = [freshness_weight(i.age_minutes) for i in cat_items]
            score = weighted_sentiment(cat_items, weights)
            setattr(intel, key, score)
