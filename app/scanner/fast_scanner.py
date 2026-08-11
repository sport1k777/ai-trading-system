"""Stage-1 fast scanner — cheap pre-filter before deep analysis."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Optional

from app.config import FAST_SCAN_CANDIDATE_COUNT
from app.scanner.parallel_runner import _auto_worker_count

logger = logging.getLogger(__name__)


@dataclass
class FastScanScore:
    symbol: str
    score: float
    atr_pct: float = 0.0
    volume_ratio: float = 0.0
    adx: float = 0.0
    trend_score: float = 0.0
    error: str = ""


def score_from_df(symbol: str, df) -> FastScanScore:
    """Score a symbol from a pre-fetched indicator dataframe."""
    if df is None or len(df) < 30:
        return FastScanScore(symbol=symbol, score=-1.0, error="insufficient_candles")

    last = df.iloc[-1]
    try:
        close = float(last["close"])
        atr = float(last.get("atr", 0))
        adx = float(last.get("adx", 0))
        ema20 = float(last.get("ema20", close))
        ema50 = float(last.get("ema50", close))
        volume_ratio = float(last.get("volume_ratio", 1.0))
    except (TypeError, ValueError, KeyError):
        return FastScanScore(symbol=symbol, score=-1.0, error="bad_indicators")

    if close <= 0 or atr <= 0:
        return FastScanScore(symbol=symbol, score=-1.0, error="invalid_price_atr")

    atr_pct = atr / close * 100.0
    score = 0.0

    score += min(max(volume_ratio, 0.0), 3.0) * 12.0
    if 0.35 <= atr_pct <= 6.0:
        score += 25.0
    elif atr_pct > 0:
        score += 10.0

    trend_score = abs(ema20 - ema50) / close * 100.0
    score += min(trend_score * 8.0, 20.0)

    if adx >= 22:
        score += min((adx - 22) * 0.8, 20.0)

    if volume_ratio >= 1.0:
        score += 10.0

    return FastScanScore(
        symbol=symbol,
        score=round(score, 2),
        atr_pct=round(atr_pct, 4),
        volume_ratio=round(volume_ratio, 3),
        adx=round(adx, 2),
        trend_score=round(trend_score, 4),
    )


def rank_symbols(
    symbols: list[str],
    fetch_fn: Callable[[str], object],
    *,
    top_n: int | None = None,
    max_workers: int | None = None,
) -> list[str]:
    """Fast-scan symbols and return the highest-scoring candidates for deep analysis."""
    if not symbols:
        return []

    top_n = top_n if top_n is not None else FAST_SCAN_CANDIDATE_COUNT
    workers = max_workers if max_workers is not None else _auto_worker_count(len(symbols))
    scores: list[FastScanScore] = []

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fastscan") as pool:
        futures = {pool.submit(fetch_fn, sym): sym for sym in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                scores.append(future.result())
            except Exception as exc:
                logger.debug("Fast scan failed for %s: %s", sym, exc)
                scores.append(FastScanScore(symbol=sym, score=-1.0, error=str(exc)))

    valid = [s for s in scores if s.score > 0]
    valid.sort(key=lambda row: row.score, reverse=True)
    selected = [s.symbol for s in valid[:top_n]]

    logger.info(
        "Fast scan | universe=%d scored=%d selected=%d top_score=%.1f",
        len(symbols),
        len(valid),
        len(selected),
        valid[0].score if valid else 0.0,
    )
    return selected
