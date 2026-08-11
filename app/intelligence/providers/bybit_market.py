"""Bybit extended public market data — funding, OI, spread, turnover."""

from __future__ import annotations

import logging
from typing import Optional

from app.config import INTELLIGENCE_BYBIT_MARKET_ENABLED
from app.intelligence.models import IntelligenceItem, ProviderResult, ReliabilityTier
from app.intelligence.providers.base import IntelligenceProvider
from app.utils.bybit_client import BybitClient

logger = logging.getLogger(__name__)


class BybitMarketProvider(IntelligenceProvider):
    name = "bybit_market"

    def __init__(self, client: Optional[BybitClient] = None):
        self._client = client

    def is_enabled(self) -> bool:
        return INTELLIGENCE_BYBIT_MARKET_ENABLED

    @property
    def client(self) -> BybitClient:
        if self._client is None:
            self._client = BybitClient()
        return self._client

    def fetch(self, symbols: list[str]) -> ProviderResult:
        if not self.is_enabled():
            return ProviderResult(self.name, False, error="disabled")

        try:
            resp = self.client.get_tickers(category="linear")
            if resp.get("retCode", 0) != 0:
                return ProviderResult(self.name, False, error=resp.get("retMsg", "tickers failed"))

            ticker_map = {
                t["symbol"]: t for t in (resp.get("result", {}).get("list") or [])
            }
            items: list[IntelligenceItem] = []
            meta: dict = {}

            for sym in symbols:
                t = ticker_map.get(sym)
                if not t:
                    continue

                bid = _f(t.get("bid1Price"))
                ask = _f(t.get("ask1Price"))
                spread_pct = ((ask - bid) / ((bid + ask) / 2) * 100) if bid and ask else None
                funding = _f(t.get("fundingRate"))
                oi = _f(t.get("openInterest"))
                turnover = _f(t.get("turnover24h"))

                meta[sym] = {
                    "spread_pct": spread_pct,
                    "funding_rate": funding,
                    "open_interest": oi,
                    "turnover_24h": turnover,
                    "last_price": _f(t.get("lastPrice")),
                }

                if funding is not None:
                    sentiment = -0.3 if funding > 0.0005 else (0.3 if funding < -0.0005 else 0.0)
                    items.append(
                        IntelligenceItem(
                            source="bybit",
                            category="market",
                            headline=f"{sym} funding rate {funding:.6f}",
                            symbol=sym,
                            sentiment=sentiment,
                            relevance=0.8,
                            reliability=ReliabilityTier.OFFICIAL,
                            raw={"funding_rate": funding, "open_interest": oi},
                        )
                    )

            return ProviderResult(self.name, True, items=items, metadata=meta)
        except Exception as exc:
            logger.warning("BybitMarketProvider failed: %s", exc)
            return ProviderResult(self.name, False, error=str(exc))


def _f(val) -> float | None:
    try:
        return float(val) if val not in (None, "", "0") else None
    except (TypeError, ValueError):
        return None
