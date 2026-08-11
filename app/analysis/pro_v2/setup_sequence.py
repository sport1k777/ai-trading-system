"""Sequential setup narrative validation."""

from __future__ import annotations

from app.analysis.market_context import MarketContext
from app.analysis.poi_proximity import near_bearish_poi, near_bullish_poi
from app.analysis.pro_v2.dealing_range import compute_dealing_range, zone_allows
from app.analysis.pro_v2.displacement import detect_displacement
from app.analysis.pro_v2.htf_bias import evaluate_htf_bias, htf_allows
from app.analysis.pro_v2.liquidity_pools import liquidity_swept_recently
from app.analysis.pro_v2.models import SetupNarrative, SetupType, SequenceStep


def _poi_return(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    price = ctx.price
    ob = ctx.order_block
    fvg = ctx.fvg

    if direction == "BUY":
        if ob and ob.get("bullish"):
            b = ob["bullish"]
            if near_bullish_poi(price, b["low"], b["high"]):
                return True, f"Return to bullish OB ({b['low']:.2f}–{b['high']:.2f})"
        if fvg and fvg.get("type") == "BULLISH":
            if near_bullish_poi(price, fvg["bottom"], fvg["top"]):
                return True, f"Return to bullish FVG ({fvg['bottom']:.2f}–{fvg['top']:.2f})"
    else:
        if ob and ob.get("bearish"):
            b = ob["bearish"]
            if near_bearish_poi(price, b["low"], b["high"]):
                return True, f"Return to bearish OB ({b['low']:.2f}–{b['high']:.2f})"
        if fvg and fvg.get("type") == "BEARISH":
            if near_bearish_poi(price, fvg["bottom"], fvg["top"]):
                return True, f"Return to bearish FVG ({fvg['bottom']:.2f}–{fvg['top']:.2f})"

    return False, "No POI return (OB/FVG)"


def _structure_break(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    if direction == "BUY":
        if ctx.bos == "BULLISH_BOS":
            return True, "Bullish BOS"
        if ctx.choch == "BULLISH_CHOCH":
            return True, "Bullish CHOCH (reversal)"
    else:
        if ctx.bos == "BEARISH_BOS":
            return True, "Bearish BOS"
        if ctx.choch == "BEARISH_CHOCH":
            return True, "Bearish CHOCH (reversal)"
    return False, "No structure break"


def _confirmation_candle(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    last = ctx.last
    close, open_ = float(last["close"]), float(last["open"])
    ratio = float(last.get("volume_ratio", 1.0))
    if direction == "BUY":
        if close > open_ and ratio >= 1.0:
            return True, f"Bullish confirmation candle (vol {ratio:.2f}x)"
    else:
        if close < open_ and ratio >= 1.0:
            return True, f"Bearish confirmation candle (vol {ratio:.2f}x)"
    return False, "No confirmation candle"


def validate_continuation(ctx: MarketContext, direction: str) -> SetupNarrative:
    dir_label: str = "LONG" if direction == "BUY" else "SHORT"
    steps: list[SequenceStep] = []

    bias = evaluate_htf_bias(ctx)
    htf_ok = htf_allows(direction, bias)
    steps.append(SequenceStep("HTF Bias", htf_ok, bias.reason))

    dealing = compute_dealing_range(ctx)
    zone_ok = zone_allows(dir_label, dealing)
    steps.append(SequenceStep("Premium/Discount", zone_ok, dealing.reason))

    sweep_ok, sweep_reason = liquidity_swept_recently(ctx, direction)
    steps.append(SequenceStep("Liquidity Sweep", sweep_ok, sweep_reason))

    disp_ok, disp_reason = detect_displacement(ctx, direction)
    steps.append(SequenceStep("Displacement", disp_ok, disp_reason))

    poi_ok, poi_reason = _poi_return(ctx, direction)
    steps.append(SequenceStep("POI Return", poi_ok, poi_reason))

    struct_ok, struct_reason = _structure_break(ctx, direction)
    steps.append(SequenceStep("Structure Break", struct_ok, struct_reason))

    confirm_ok, confirm_reason = _confirmation_candle(ctx, direction)
    steps.append(SequenceStep("Confirmation", confirm_ok, confirm_reason))

    required = {"HTF Bias", "Liquidity Sweep", "Displacement", "POI Return", "Structure Break", "Confirmation"}
    completed = {s.name for s in steps if s.completed}
    complete = required.issubset(completed) and zone_ok

    return SetupNarrative(
        setup_type=SetupType.CONTINUATION,
        direction=dir_label,
        steps=steps,
        complete=complete,
        summary=f"Continuation {dir_label}: {len(completed)}/{len(steps)} steps",
    )


def validate_reversal(ctx: MarketContext, direction: str) -> SetupNarrative:
    dir_label = "LONG" if direction == "BUY" else "SHORT"
    steps: list[SequenceStep] = []

    sweep_ok, sweep_reason = liquidity_swept_recently(ctx, direction)
    steps.append(SequenceStep("Liquidity Sweep", sweep_ok, sweep_reason))

    if direction == "BUY":
        choch_ok = ctx.choch == "BULLISH_CHOCH"
    else:
        choch_ok = ctx.choch == "BEARISH_CHOCH"
    steps.append(SequenceStep("CHOCH", choch_ok, ctx.choch))

    poi_ok, poi_reason = _poi_return(ctx, direction)
    steps.append(SequenceStep("POI Return", poi_ok, poi_reason))

    disp_ok, disp_reason = detect_displacement(ctx, direction)
    steps.append(SequenceStep("Displacement", disp_ok, disp_reason))

    confirm_ok, confirm_reason = _confirmation_candle(ctx, direction)
    steps.append(SequenceStep("Confirmation", confirm_ok, confirm_reason))

    required = {"Liquidity Sweep", "CHOCH", "POI Return", "Displacement", "Confirmation"}
    completed = {s.name for s in steps if s.completed}
    complete = required.issubset(completed)

    return SetupNarrative(
        setup_type=SetupType.REVERSAL,
        direction=dir_label,
        steps=steps,
        complete=complete,
        summary=f"Reversal {dir_label}: {len(completed)}/{len(steps)} steps",
    )


def pick_best_narrative(ctx: MarketContext) -> SetupNarrative:
    long_cont = validate_continuation(ctx, "BUY")
    short_cont = validate_continuation(ctx, "SELL")
    long_rev = validate_reversal(ctx, "BUY")
    short_rev = validate_reversal(ctx, "SELL")

    candidates = [long_cont, short_cont, long_rev, short_rev]
    complete = [c for c in candidates if c.complete]
    if not complete:
        best = max(candidates, key=lambda c: sum(s.completed for s in c.steps))
        return best

    return max(complete, key=lambda c: sum(s.completed for s in c.steps))


def pick_best_narrative_for_direction(ctx: MarketContext, direction: str) -> SetupNarrative:
    """Best continuation or reversal narrative for a fixed direction."""
    cont = validate_continuation(ctx, direction)
    rev = validate_reversal(ctx, direction)
    candidates = [cont, rev]
    complete = [c for c in candidates if c.complete]
    if complete:
        return max(complete, key=lambda c: sum(s.completed for s in c.steps))
    return max(candidates, key=lambda c: sum(s.completed for s in c.steps))


def confluence_core_aligned(ctx: MarketContext, direction: str) -> tuple[bool, str]:
    """BOS + order block + liquidity sweep + EMA stack (CHOCH optional)."""
    if direction not in ("BUY", "SELL"):
        return False, "No direction"

    struct_ok, struct_reason = _structure_break(ctx, direction)
    if not struct_ok:
        return False, struct_reason

    sweep_ok, sweep_reason = liquidity_swept_recently(ctx, direction)
    if not sweep_ok:
        return False, sweep_reason

    ob = ctx.order_block
    if direction == "BUY":
        if not ob or not ob.get("bullish"):
            return False, "No bullish order block"
        block = ob["bullish"]
        if not near_bullish_poi(ctx.price, block["low"], block["high"]):
            return False, "Price not at bullish order block"
    else:
        if not ob or not ob.get("bearish"):
            return False, "No bearish order block"
        block = ob["bearish"]
        if not near_bearish_poi(ctx.price, block["low"], block["high"]):
            return False, "Price not at bearish order block"

    last = ctx.last
    ema20 = float(last.get("ema20", 0))
    ema50 = float(last.get("ema50", 0))
    close = float(last.get("close", 0))
    if direction == "BUY":
        if not (ema20 > ema50 and close > ema50):
            return False, "EMA stack not bullish"
    else:
        if not (ema20 < ema50 and close < ema50):
            return False, "EMA stack not bearish"

    return True, "BOS+OB+liquidity+EMA aligned"
