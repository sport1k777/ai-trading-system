"""Higher-timeframe bias engine for PRO V2."""

from __future__ import annotations

import logging

from app.analysis.market_context import MarketContext
from app.analysis.pro_v2.models import HTFBias

logger = logging.getLogger(__name__)


def evaluate_htf_bias(ctx: MarketContext) -> HTFBias:
    trend = ctx.htf_trend
    structure = ctx.htf_structure
    bos = ctx.htf_bos

    if trend == "BULLISH" and structure in ("UPTREND", "RANGE"):
        strength = 90.0 if structure == "UPTREND" else 70.0
        if bos == "BULLISH_BOS":
            strength = min(100.0, strength + 10)
        return HTFBias(
            direction="LONG",
            trend=trend,
            structure=structure,
            bos=bos,
            reason=f"HTF bullish bias ({structure}, {bos})",
            strength=strength,
        )

    if trend == "BEARISH" and structure in ("DOWNTREND", "RANGE"):
        strength = 90.0 if structure == "DOWNTREND" else 70.0
        if bos == "BEARISH_BOS":
            strength = min(100.0, strength + 10)
        return HTFBias(
            direction="SHORT",
            trend=trend,
            structure=structure,
            bos=bos,
            reason=f"HTF bearish bias ({structure}, {bos})",
            strength=strength,
        )

    logger.debug("HTF bias neutral: trend=%s structure=%s", trend, structure)
    return HTFBias(
        direction=None,
        trend=trend,
        structure=structure,
        bos=bos,
        reason=f"HTF neutral ({trend}/{structure})",
        strength=40.0,
    )


def htf_allows(direction: str, bias: HTFBias) -> bool:
    if bias.direction is None:
        return False
    if direction == "BUY":
        return bias.direction == "LONG"
    if direction == "SELL":
        return bias.direction == "SHORT"
    return False
