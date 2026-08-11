"""Regime and volatility gates for PRO V2."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.analysis.market_context import MarketContext
from app.analysis.pro.conditions import is_volatility_tradeable
from app.analysis.pro_v2.models import GateResult
from app.config import PRO_V2_MIN_ADX, PRO_V2_SESSION_FILTER

logger = logging.getLogger(__name__)

PREFERRED_HOURS_UTC = {7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20}


def check_atr_gate(ctx: MarketContext) -> GateResult:
    ok, reason = is_volatility_tradeable(ctx.last)
    return GateResult("ATR Volatility", ok, reason, blocking=True)


def check_adx_gate(ctx: MarketContext, *, for_trend_setup: bool = True) -> GateResult:
    adx = float(ctx.last.get("adx", 0))
    if for_trend_setup:
        passed = adx >= PRO_V2_MIN_ADX
        reason = f"ADX {adx:.1f} (min {PRO_V2_MIN_ADX})" if passed else (
            f"ADX {adx:.1f} below trend threshold {PRO_V2_MIN_ADX}"
        )
    else:
        passed = adx <= PRO_V2_MIN_ADX + 5
        reason = f"ADX {adx:.1f} suitable for range/reversal" if passed else (
            f"ADX {adx:.1f} too strong for reversal setup"
        )
    return GateResult("ADX Trend", passed, reason, blocking=True)


def check_session_gate(ctx: MarketContext) -> GateResult:
    if not PRO_V2_SESSION_FILTER:
        return GateResult("Session", True, "Session filter disabled", blocking=False)

    ts = ctx.analysis_df.iloc[-1].get("timestamp")
    hour = datetime.now(timezone.utc).hour
    if ts is not None:
        try:
            hour = pd_timestamp_hour(ts)
        except Exception:
            pass

    passed = hour in PREFERRED_HOURS_UTC
    reason = f"UTC hour {hour} {'in' if passed else 'outside'} preferred session"
    return GateResult("Session", passed, reason, blocking=False)


def pd_timestamp_hour(ts) -> int:
    import pandas as pd
    if isinstance(ts, str):
        ts = pd.to_datetime(ts)
    if hasattr(ts, "hour"):
        return int(ts.hour)
    return int(pd.to_datetime(ts, utc=True).hour)


def check_structure_alignment(
    ctx: MarketContext,
    direction: str,
    *,
    allow_override: bool = False,
) -> GateResult:
    structure = ctx.structure
    if direction == "BUY":
        passed = structure in ("UPTREND", "RANGE")
        reason = f"LTF structure {structure} allows long" if passed else (
            f"LTF structure {structure} blocks long"
        )
    else:
        passed = structure in ("DOWNTREND", "RANGE")
        reason = f"LTF structure {structure} allows short" if passed else (
            f"LTF structure {structure} blocks short"
        )

    if not passed and allow_override:
        return GateResult(
            "Structure Alignment",
            True,
            f"{reason} — confluence core override",
            blocking=True,
        )
    return GateResult("Structure Alignment", passed, reason, blocking=True)


def run_regime_gates(
    ctx: MarketContext,
    direction: str | None = None,
    *,
    allow_bos_structure_override: bool = False,
) -> list[GateResult]:
    gates = [check_atr_gate(ctx), check_adx_gate(ctx)]
    gates.append(check_session_gate(ctx))
    if direction in ("BUY", "SELL"):
        gates.append(
            check_structure_alignment(
                ctx,
                direction,
                allow_override=allow_bos_structure_override,
            )
        )
    return gates
