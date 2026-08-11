"""Bybit linear USDT perpetual symbol discovery and filtering."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.config import (
    SCANNER_MAX_SPREAD_PCT,
    SCANNER_MIN_TURNOVER_24H,
    SCANNER_SYMBOL_TARGET,
    SCANNER_SYMBOLS,
    SCANNER_UNIVERSE_CACHE_SECONDS,
)
from app.utils.bybit_client import BybitClient

logger = logging.getLogger(__name__)

_cache: dict = {"symbols": [], "fetched_at": 0.0}


@dataclass
class SymbolFilterStats:
    total_instruments: int = 0
    after_usdt_filter: int = 0
    after_status_filter: int = 0
    after_liquidity_filter: int = 0
    selected: int = 0


def _parse_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _spread_pct(ticker: dict) -> float:
    bid = _parse_float(ticker.get("bid1Price"))
    ask = _parse_float(ticker.get("ask1Price"))
    if bid <= 0 or ask <= 0:
        return 999.0
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 999.0
    return (ask - bid) / mid * 100.0


def fetch_linear_usdt_universe(
    client: BybitClient | None = None,
    *,
    target: int | None = None,
    min_turnover: float | None = None,
    max_spread_pct: float | None = None,
) -> tuple[list[str], SymbolFilterStats]:
    """Return ranked Bybit linear USDT perpetual symbols passing liquidity filters."""
    target = target if target is not None else SCANNER_SYMBOL_TARGET
    min_turnover = min_turnover if min_turnover is not None else SCANNER_MIN_TURNOVER_24H
    max_spread_pct = max_spread_pct if max_spread_pct is not None else SCANNER_MAX_SPREAD_PCT
    client = client or BybitClient()
    stats = SymbolFilterStats()

    inst_resp = client.get_instruments_info(category="linear", limit=1000)
    if inst_resp.get("retCode", 0) != 0:
        raise RuntimeError(inst_resp.get("retMsg", "instruments-info failed"))

    instruments = inst_resp.get("result", {}).get("list") or []
    stats.total_instruments = len(instruments)

    usdt_perps = [
        i for i in instruments
        if i.get("quoteCoin") == "USDT"
        and i.get("settleCoin") == "USDT"
        and str(i.get("symbol", "")).endswith("USDT")
    ]
    stats.after_usdt_filter = len(usdt_perps)

    tradable = [
        i for i in usdt_perps
        if i.get("status") == "Trading"
        and i.get("contractType") in ("LinearPerpetual", "LinearFutures", None)
        and str(i.get("symbol", "")).endswith("USDT")
    ]
    stats.after_status_filter = len(tradable)

    ticker_resp = client.get_tickers(category="linear")
    if ticker_resp.get("retCode", 0) != 0:
        raise RuntimeError(ticker_resp.get("retMsg", "tickers failed"))

    ticker_map = {
        t["symbol"]: t for t in (ticker_resp.get("result", {}).get("list") or [])
    }

    ranked: list[tuple[str, float]] = []
    for inst in tradable:
        sym = inst["symbol"]
        ticker = ticker_map.get(sym)
        if not ticker:
            continue

        turnover = _parse_float(ticker.get("turnover24h"))
        volume = _parse_float(ticker.get("volume24h"))
        spread = _spread_pct(ticker)

        if turnover < min_turnover and volume <= 0:
            continue
        if spread > max_spread_pct:
            continue

        ranked.append((sym, turnover))

    stats.after_liquidity_filter = len(ranked)
    ranked.sort(key=lambda row: row[1], reverse=True)

    symbols = [sym for sym, _ in ranked[:target]]

    # Always include configured priority symbols at the front.
    priority = [s for s in SCANNER_SYMBOLS if s in {sym for sym, _ in ranked}]
    merged: list[str] = []
    for sym in priority + symbols:
        if sym not in merged:
            merged.append(sym)
    symbols = merged[:target]
    stats.selected = len(symbols)

    logger.info(
        "Symbol universe | total=%d usdt=%d tradable=%d liquid=%d selected=%d",
        stats.total_instruments,
        stats.after_usdt_filter,
        stats.after_status_filter,
        stats.after_liquidity_filter,
        stats.selected,
    )
    return symbols, stats


def get_scan_symbols(
    client: BybitClient | None = None,
    *,
    force_refresh: bool = False,
) -> list[str]:
    """Cached symbol list for the scanner service."""
    now = time.time()
    if (
        not force_refresh
        and _cache["symbols"]
        and now - _cache["fetched_at"] < SCANNER_UNIVERSE_CACHE_SECONDS
    ):
        return list(_cache["symbols"])

    if SCANNER_SYMBOL_TARGET <= len(SCANNER_SYMBOLS) and not force_refresh:
        return list(SCANNER_SYMBOLS)

    try:
        symbols, _ = fetch_linear_usdt_universe(client=client)
        _cache["symbols"] = symbols
        _cache["fetched_at"] = now
        return symbols
    except Exception:
        logger.exception("Symbol universe fetch failed; using static SCANNER_SYMBOLS")
        return list(SCANNER_SYMBOLS)
