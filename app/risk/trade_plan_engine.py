"""Authoritative trade-plan builder — single source of truth for entry/SL/TP/R:R.

All Telegram alerts must use values produced here (via RiskManagerV2 / normalize_risk_dict).
Structural targets only — no mechanical fixed-percentage padding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from app.analysis.market_context import MarketContext
from app.analysis.poi_proximity import near_zone
from app.config import (
    MAX_STOP_ATR_MULT,
    MIN_STOP_ATR_MULT,
    STOP_ATR_MULT,
    TP_MIN_RR_TP1,
    TP_MIN_RR_TP2,
    TP_MIN_RR_TP3,
    VALIDATION_ENTRY_MAX_DISTANCE_PCT,
)
from app.risk.signal_levels import compute_rr, validate_signal_risk


def _pct_distance(base: float, target: float) -> float:
    if base == 0:
        return 0.0
    return abs(target - base) / abs(base) * 100.0


def _round_price(price: float) -> float:
    if price >= 1000:
        return round(price, 2)
    if price >= 1:
        return round(price, 4)
    return round(price, 6)


def _min_step(entry: float, risk_dist: float) -> float:
    return max(risk_dist * 0.08, abs(entry) * 1e-6, 1e-8)


def _dedupe_levels(levels: list[float], entry: float, *, min_step: float) -> list[float]:
    distinct: list[float] = []
    for price in levels:
        rp = _round_price(price)
        if not distinct:
            distinct.append(rp)
            continue
        if all(abs(rp - existing) >= min_step for existing in distinct):
            distinct.append(rp)
    return distinct


@dataclass
class TradePlan:
    entry: float
    stop: float
    tp1: float
    tp2: float
    tp3: float
    entry_type: str
    current_price: float
    entry_distance_pct: float
    risk: float
    risk_pct: float
    reward_tp1_pct: float
    reward_tp2_pct: float
    reward_tp3_pct: float
    rr_tp1: float
    rr_tp2: float
    rr_tp3: float

    @property
    def rr(self) -> float:
        return self.rr_tp1

    def to_risk_dict(self) -> dict:
        return {
            "entry": _round_price(self.entry),
            "stop": _round_price(self.stop),
            "tp1": _round_price(self.tp1),
            "tp2": _round_price(self.tp2),
            "tp3": _round_price(self.tp3),
            "tp": _round_price(self.tp1),
            "risk": round(self.risk, 4),
            "rr": self.rr_tp1,
            "rr_tp1": self.rr_tp1,
            "rr_tp2": self.rr_tp2,
            "rr_tp3": self.rr_tp3,
            "risk_pct": round(self.risk_pct, 4),
            "reward_tp1_pct": round(self.reward_tp1_pct, 4),
            "reward_tp2_pct": round(self.reward_tp2_pct, 4),
            "reward_tp3_pct": round(self.reward_tp3_pct, 4),
            "entry_type": self.entry_type,
            "current_price": _round_price(self.current_price),
            "entry_distance_pct": round(self.entry_distance_pct, 4),
        }


def _resolve_entry(ctx: MarketContext, direction: str) -> tuple[float, str, float]:
    """Market vs limit entry at structural POI."""
    price = ctx.price
    ob = ctx.order_block
    side = "bullish" if direction == "BUY" else "bearish"
    zone = ob.get(side) if ob else None

    if zone:
        low, high = float(zone["low"]), float(zone["high"])
        mid = (low + high) / 2.0
        if near_zone(price, low, high) or _pct_distance(price, mid) <= VALIDATION_ENTRY_MAX_DISTANCE_PCT:
            if direction == "BUY":
                entry = _round_price(min(mid, high))
            else:
                entry = _round_price(max(mid, low))
            return entry, "limit", price

    if ctx.fvg:
        fvg_type = str(ctx.fvg.get("type", "")).upper()
        bottom = ctx.fvg.get("bottom")
        top = ctx.fvg.get("top")
        if bottom is not None and top is not None:
            fvg_mid = (float(bottom) + float(top)) / 2.0
            if near_zone(price, float(bottom), float(top)):
                if direction == "BUY" and fvg_type == "BULLISH":
                    return _round_price(fvg_mid), "limit", price
                if direction == "SELL" and fvg_type == "BEARISH":
                    return _round_price(fvg_mid), "limit", price

    return _round_price(price), "market", price


def _resolve_stop(
    ctx: MarketContext,
    direction: str,
    entry: float,
    *,
    swing_low: float | None,
    swing_high: float | None,
    atr: float,
) -> float | None:
    """Structural stop with ATR sanity bounds."""
    stop_mult = STOP_ATR_MULT * 0.9

    if direction == "BUY":
        atr_stop = entry - stop_mult * atr
        structure_stop = (swing_low - 0.2 * atr) if swing_low is not None else atr_stop
        stop = min(atr_stop, structure_stop)
        stop = max(stop, entry - MAX_STOP_ATR_MULT * atr)
        ob = ctx.order_block.get("bullish") if ctx.order_block else None
        if ob:
            stop = min(stop, float(ob["low"]) - 0.05 * atr)
        if ctx.liquidity and ctx.liquidity.get("type") == "SELL_SIDE_SWEEP":
            liq = float(ctx.liquidity.get("level", stop))
            structural = liq - 0.1 * atr
            if structural < stop:
                stop = structural
    else:
        atr_stop = entry + stop_mult * atr
        structure_stop = (swing_high + 0.2 * atr) if swing_high is not None else atr_stop
        stop = max(atr_stop, structure_stop)
        stop = min(stop, entry + MAX_STOP_ATR_MULT * atr)
        ob = ctx.order_block.get("bearish") if ctx.order_block else None
        if ob:
            stop = max(stop, float(ob["high"]) + 0.05 * atr)
        if ctx.liquidity and ctx.liquidity.get("type") == "BUY_SIDE_SWEEP":
            liq = float(ctx.liquidity.get("level", stop))
            structural = liq + 0.1 * atr
            if structural > stop:
                stop = structural

    stop = _round_price(stop)
    risk_dist = abs(entry - stop)
    if risk_dist <= 0:
        return None
    if risk_dist > MAX_STOP_ATR_MULT * atr:
        return None
    if risk_dist < MIN_STOP_ATR_MULT * atr:
        return None
    return stop


def _collect_structural_targets(ctx: MarketContext, direction: str, entry: float) -> list[float]:
    """Liquidity pools, swings, POC, FVG, HTF extremes — no fixed-percent offsets."""
    from app.analysis.pro_v2.liquidity_pools import detect_liquidity_pools

    pools = detect_liquidity_pools(ctx)
    raw: list[float] = []

    poc = ctx.last.get("poc")
    if poc is not None and pd.notna(poc):
        raw.append(float(poc))

    if direction == "BUY":
        raw.extend(float(p) for p in (pools.get("buy_side_pools") or []) if float(p) > entry)
        raw.extend(float(sh["price"]) for sh in (ctx.swing_highs or []) if float(sh["price"]) > entry)
        if ctx.fvg and str(ctx.fvg.get("type", "")).upper() == "BULLISH":
            for key in ("top", "bottom"):
                val = ctx.fvg.get(key)
                if val is not None and float(val) > entry:
                    raw.append(float(val))
        if ctx.htf_df is not None and len(ctx.htf_df) >= 5:
            htf_high = float(ctx.htf_df["high"].astype(float).max())
            if htf_high > entry:
                raw.append(htf_high)
        ordered = sorted(set(raw))
    else:
        raw.extend(float(p) for p in (pools.get("sell_side_pools") or []) if float(p) < entry)
        raw.extend(float(sl["price"]) for sl in (ctx.swing_lows or []) if float(sl["price"]) < entry)
        if ctx.fvg and str(ctx.fvg.get("type", "")).upper() == "BEARISH":
            for key in ("top", "bottom"):
                val = ctx.fvg.get(key)
                if val is not None and float(val) < entry:
                    raw.append(float(val))
        if ctx.htf_df is not None and len(ctx.htf_df) >= 5:
            htf_low = float(ctx.htf_df["low"].astype(float).min())
            if htf_low < entry:
                raw.append(htf_low)
        ordered = sorted(set(raw), reverse=True)

    return _dedupe_levels(ordered, entry, min_step=_min_step(entry, max(abs(entry) * 0.001, 1e-6)))


def _select_tp_ladder(
    direction: str,
    entry: float,
    stop: float,
    candidates: list[float],
    *,
    min_rrs: tuple[float, float, float] = (TP_MIN_RR_TP1, TP_MIN_RR_TP2, TP_MIN_RR_TP3),
) -> tuple[float, float, float] | None:
    """Pick three distinct structural targets each meeting minimum R-multiple floors."""
    risk = abs(entry - stop)
    if risk <= 0:
        return None

    min_step = _min_step(entry, risk)
    selected: list[float] = []

    for mult in min_rrs:
        floor = entry + mult * risk if direction == "BUY" else entry - mult * risk
        if direction == "BUY":
            valid = [c for c in candidates if c >= floor - min_step * 0.5]
            valid = sorted(valid)
        else:
            valid = [c for c in candidates if c <= floor + min_step * 0.5]
            valid = sorted(valid, reverse=True)

        pick: float | None = None
        for candidate in valid:
            cand = _round_price(candidate)
            if selected and abs(cand - selected[-1]) < min_step:
                continue
            if direction == "BUY" and cand <= entry + min_step:
                continue
            if direction == "SELL" and cand >= entry - min_step:
                continue
            pick = cand
            break

        if pick is None:
            return None
        selected.append(pick)

    tp1, tp2, tp3 = selected[0], selected[1], selected[2]

    if direction == "BUY":
        if not (stop < entry < tp1 < tp2 < tp3):
            return None
    else:
        if not (tp3 < tp2 < tp1 < entry < stop):
            return None

    if len({round(tp1, 8), round(tp2, 8), round(tp3, 8)}) < 3:
        return None

    rr1 = compute_rr(entry, stop, tp1)
    rr2 = compute_rr(entry, stop, tp2)
    rr3 = compute_rr(entry, stop, tp3)
    if rr1 < min_rrs[0] or rr2 < min_rrs[1] or rr3 < min_rrs[2]:
        return None

    return tp1, tp2, tp3


def build_trade_plan(
    ctx: MarketContext,
    direction: str,
    *,
    swing_low: float | None = None,
    swing_high: float | None = None,
) -> dict | None:
    """Build a validated trade plan or return None when structure cannot support it."""
    if direction not in ("BUY", "SELL"):
        return None

    atr = ctx.atr
    if atr is None or atr <= 0:
        return None

    entry, entry_type, current_price = _resolve_entry(ctx, direction)
    stop = _resolve_stop(
        ctx,
        direction,
        entry,
        swing_low=swing_low,
        swing_high=swing_high,
        atr=atr,
    )
    if stop is None and entry_type == "limit":
        entry = _round_price(current_price)
        entry_type = "market"
        stop = _resolve_stop(
            ctx,
            direction,
            entry,
            swing_low=swing_low,
            swing_high=swing_high,
            atr=atr,
        )
    if stop is None:
        return None

    risk_dist = abs(entry - stop)
    entry_distance_pct = _pct_distance(current_price, entry)
    if entry_distance_pct > VALIDATION_ENTRY_MAX_DISTANCE_PCT:
        return None

    candidates = _collect_structural_targets(ctx, direction, entry)
    ladder = _select_tp_ladder(direction, entry, stop, candidates)
    if not ladder:
        return None

    tp1, tp2, tp3 = ladder
    plan = TradePlan(
        entry=entry,
        stop=stop,
        tp1=tp1,
        tp2=tp2,
        tp3=tp3,
        entry_type=entry_type,
        current_price=current_price,
        entry_distance_pct=entry_distance_pct,
        risk=risk_dist,
        risk_pct=_pct_distance(entry, stop),
        reward_tp1_pct=_pct_distance(entry, tp1),
        reward_tp2_pct=_pct_distance(entry, tp2),
        reward_tp3_pct=_pct_distance(entry, tp3),
        rr_tp1=compute_rr(entry, stop, tp1),
        rr_tp2=compute_rr(entry, stop, tp2),
        rr_tp3=compute_rr(entry, stop, tp3),
    )

    risk_dict = plan.to_risk_dict()
    ok, _ = validate_signal_risk(direction, risk_dict)
    return risk_dict if ok else None
