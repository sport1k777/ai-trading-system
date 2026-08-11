"""RSS/news provider — legitimate public feeds only; never fabricates headlines."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.request import Request, urlopen

from app.config import INTELLIGENCE_NEWS_ENABLED, INTELLIGENCE_NEWS_RSS_URLS
from app.intelligence.freshness import is_stale_for_signals
from app.intelligence.models import IntelligenceItem, ProviderResult, ReliabilityTier
from app.intelligence.providers.base import IntelligenceProvider

logger = logging.getLogger(__name__)

_NEGATIVE = re.compile(
    r"\b(hack|exploit|breach|sec|lawsuit|ban|delist|crash|fraud|scam|rug)\b",
    re.I,
)
_POSITIVE = re.compile(
    r"\b(partnership|launch|listing|upgrade|approval|etf|integration|record)\b",
    re.I,
)
_BLOCKING = re.compile(
    r"\b(hack|exploit|breach|rug pull|delist|security breach)\b",
    re.I,
)


class NewsRssProvider(IntelligenceProvider):
    name = "news_rss"

    def is_enabled(self) -> bool:
        return INTELLIGENCE_NEWS_ENABLED and bool(INTELLIGENCE_NEWS_RSS_URLS)

    def fetch(self, symbols: list[str]) -> ProviderResult:
        if not self.is_enabled():
            return ProviderResult(self.name, False, error="disabled or no RSS URLs configured")

        keywords = _symbol_keywords(symbols)
        items: list[IntelligenceItem] = []
        errors: list[str] = []

        for url in INTELLIGENCE_NEWS_RSS_URLS:
            try:
                items.extend(self._parse_feed(url, keywords))
            except Exception as exc:
                errors.append(f"{url}: {exc}")
                logger.debug("RSS fetch failed for %s: %s", url, exc)

        if not items and errors:
            return ProviderResult(self.name, False, error="; ".join(errors[:3]))

        return ProviderResult(
            self.name,
            True,
            items=items,
            metadata={"feeds": len(INTELLIGENCE_NEWS_RSS_URLS), "errors": errors},
        )

    def _parse_feed(self, url: str, keywords: dict[str, list[str]]) -> list[IntelligenceItem]:
        req = Request(url, headers={"User-Agent": "AI-Signal-Intelligence/1.0"})
        with urlopen(req, timeout=10) as resp:
            content = resp.read()

        root = ET.fromstring(content)
        channel = root.find("channel")
        entries = list(root.findall(".//item"))
        if channel is not None:
            entries = channel.findall("item") or entries

        out: list[IntelligenceItem] = []
        for item in entries[:40]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or item.findtext("summary") or "").strip()
            pub = item.findtext("pubDate") or item.findtext("published") or ""
            published = _parse_date(pub)
            text = f"{title} {desc}".lower()

            matched_syms = [
                sym for sym, kws in keywords.items() if any(kw in text for kw in kws)
            ]
            if not matched_syms:
                continue

            age_min = (
                (datetime.now(timezone.utc) - published).total_seconds() / 60.0
                if published
                else 9999.0
            )
            if is_stale_for_signals(age_min):
                continue

            sentiment = 0.0
            if _NEGATIVE.search(text):
                sentiment -= 0.6
            if _POSITIVE.search(text):
                sentiment += 0.5
            blocking = bool(_BLOCKING.search(text))

            for sym in matched_syms:
                out.append(
                    IntelligenceItem(
                        source=_feed_source(url),
                        category="news",
                        headline=title[:300],
                        summary=desc[:500],
                        url=link,
                        symbol=sym,
                        sentiment=max(-1.0, min(1.0, sentiment)),
                        relevance=0.9 if sym.replace("USDT", "").lower() in text else 0.6,
                        reliability=ReliabilityTier.REPUTABLE,
                        published_at=published,
                        is_blocking=blocking,
                        block_reason=f"Negative news: {title[:80]}" if blocking else "",
                    )
                )
        return out


def _symbol_keywords(symbols: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sym in symbols:
        base = sym.replace("USDT", "").lower()
        out[sym] = [base, sym.lower()]
        if base == "btc":
            out[sym].extend(["bitcoin"])
        elif base == "eth":
            out[sym].extend(["ethereum"])
        elif base == "sol":
            out[sym].extend(["solana"])
    return out


def _parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _feed_source(url: str) -> str:
    if "coindesk" in url:
        return "coindesk_rss"
    if "cointelegraph" in url:
        return "cointelegraph_rss"
    return "rss"
