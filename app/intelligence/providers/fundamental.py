"""Fundamental data via public CoinGecko API — read-only, no fabrication."""

from __future__ import annotations

import json
import logging
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.config import INTELLIGENCE_FUNDAMENTAL_ENABLED
from app.intelligence.models import IntelligenceItem, ProviderResult, ReliabilityTier
from app.intelligence.providers.base import IntelligenceProvider

logger = logging.getLogger(__name__)

COINGECKO_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "XRPUSDT": "ripple",
    "DOGEUSDT": "dogecoin",
    "BNBUSDT": "binancecoin",
    "ADAUSDT": "cardano",
    "AVAXUSDT": "avalanche-2",
    "LINKUSDT": "chainlink",
    "DOTUSDT": "polkadot",
}


class FundamentalProvider(IntelligenceProvider):
    name = "fundamental"

    def is_enabled(self) -> bool:
        return INTELLIGENCE_FUNDAMENTAL_ENABLED

    def fetch(self, symbols: list[str]) -> ProviderResult:
        if not self.is_enabled():
            return ProviderResult(self.name, False, error="disabled")

        items: list[IntelligenceItem] = []
        meta: dict = {}
        errors: list[str] = []

        for sym in symbols:
            coin_id = COINGECKO_MAP.get(sym)
            if not coin_id:
                meta[sym] = {"status": "no_mapping"}
                continue
            try:
                data = self._fetch_coin(coin_id)
                meta[sym] = data
                mc_change = data.get("market_cap_change_24h")
                sentiment = 0.0
                if mc_change is not None:
                    if mc_change > 5:
                        sentiment = 0.3
                    elif mc_change < -5:
                        sentiment = -0.3
                items.append(
                    IntelligenceItem(
                        source="coingecko",
                        category="fundamental",
                        headline=f"{sym} market cap rank #{data.get('market_cap_rank', 'n/a')}",
                        symbol=sym,
                        sentiment=sentiment,
                        relevance=0.7,
                        reliability=ReliabilityTier.REPUTABLE,
                        raw=data,
                    )
                )
            except Exception as exc:
                errors.append(f"{sym}: {exc}")

        if not items and errors:
            return ProviderResult(self.name, False, error="; ".join(errors[:3]))

        return ProviderResult(self.name, True, items=items, metadata=meta, error="; ".join(errors))

    def _fetch_coin(self, coin_id: str) -> dict:
        url = f"https://api.coingecko.com/api/v3/coins/{quote(coin_id)}?localization=false&tickers=false&community_data=false&developer_data=false"
        req = Request(url, headers={"User-Agent": "AI-Signal-Intelligence/1.0", "Accept": "application/json"})
        with urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode())
        md = data.get("market_data") or {}
        return {
            "id": coin_id,
            "market_cap_rank": data.get("market_cap_rank"),
            "market_cap_usd": md.get("market_cap", {}).get("usd"),
            "fdv_usd": md.get("fully_diluted_valuation", {}).get("usd"),
            "circulating_supply": md.get("circulating_supply"),
            "market_cap_change_24h": md.get("market_cap_change_percentage_24h"),
        }
