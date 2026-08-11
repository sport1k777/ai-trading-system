"""Premium institutional Telegram formatting for AI trading signals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, Optional

import pandas as pd

from app.config import DEFAULT_INTERVAL
from app.risk.signal_levels import compute_rr
from app.validation import validate_signal

if TYPE_CHECKING:
    from app.pipeline import AnalysisResult

INTERVAL_LABELS = {
    "1": "1m",
    "3": "3m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "120": "2h",
    "240": "4h",
    "360": "6h",
    "720": "12h",
    "D": "1D",
    "W": "1W",
}

INTERVAL_MINUTES = {
    "1": 1,
    "3": 3,
    "5": 5,
    "15": 15,
    "30": 30,
    "60": 60,
    "120": 120,
    "240": 240,
    "360": 360,
    "720": 720,
    "D": 1440,
    "W": 10080,
}

GRADE_ICONS = {
    "A+": "🏆",
    "A": "⭐",
    "B": "✦",
    "C": "◦",
}

BOS_LABELS = {
    "BULLISH_BOS": "Bullish BOS",
    "BEARISH_BOS": "Bearish BOS",
    "NO_BOS": "No BOS",
}

CHOCH_LABELS = {
    "BULLISH_CHOCH": "Bullish CHOCH",
    "BEARISH_CHOCH": "Bearish CHOCH",
    "NO_CHOCH": "No CHOCH",
}

LIQUIDITY_LABELS = {
    "BUY_SIDE_SWEEP": "Buy\\-side sweep",
    "SELL_SIDE_SWEEP": "Sell\\-side sweep",
}


def format_timeframe(interval: str) -> str:
    return INTERVAL_LABELS.get(interval, interval)


def _md_escape(text: str) -> str:
    """Escape text for Telegram MarkdownV2."""
    for char in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(char, f"\\{char}")
    return text


def _divider(width: int = 24) -> str:
    return "─" * width


def _section(title: str) -> str:
    return f"\n*▸ {_md_escape(title.upper())}*\n{_divider()}"


def _price(value: float) -> str:
    if value >= 1000:
        formatted = f"{value:,.2f}"
    elif value >= 1:
        formatted = f"{value:,.4f}"
    else:
        formatted = f"{value:,.6f}"
    return f"`{formatted}`"


def _pct_change(base: float, target: float) -> str:
    if base == 0:
        return "0\\.00%"
    pct = (target - base) / base * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _confidence_bar(confidence: float, width: int = 12) -> str:
    clamped = max(0.0, min(100.0, confidence))
    filled = round(clamped / 100 * width)
    return "█" * filled + "░" * (width - filled)


def _grade_display(grade: str) -> str:
    icon = GRADE_ICONS.get(grade, "◦")
    if grade in ("—", "", "None"):
        return f"{icon} {_md_escape('N/A')}"
    return f"{icon} *{_md_escape(grade)}*"


def _fs_by_name(feature_scores: list[dict]) -> dict[str, dict]:
    return {fs["name"]: fs for fs in feature_scores}


def _score_aligned(fs: dict | None, direction: str, threshold: float = 70.0) -> bool:
    if not fs:
        return False
    score = fs["buy_score"] if direction == "BUY" else fs["sell_score"]
    return float(score) >= threshold


def _names_aligned(
    by_name: dict[str, dict],
    names: tuple[str, ...],
    direction: str,
    threshold: float = 70.0,
) -> bool:
    for name in names:
        if _score_aligned(by_name.get(name), direction, threshold):
            return True
    return False


def _gate_passed(gates: list[str], *needles: str) -> bool:
    joined = " ".join(gates).lower()
    return any(n.lower() in joined for n in needles)


def _resolve_orderblock(signal: dict, result: AnalysisResult) -> dict | None:
    return signal.get("orderblock") or result.order_block


def _resolve_liquidity(signal: dict, result: AnalysisResult) -> dict | None:
    return signal.get("liquidity") or result.liquidity


def _resolve_fvg(signal: dict, result: AnalysisResult) -> dict | None:
    return signal.get("fvg") or result.fvg


def _format_htf_bias(signal: dict) -> str:
    htf = (signal.get("htf_bias") or "").strip()
    zone = (signal.get("dealing_range_zone") or "").strip()
    if htf and zone:
        return _md_escape(f"{htf} · {zone}")
    if htf:
        return _md_escape(htf)
    if zone:
        return _md_escape(zone)
    return _md_escape("Neutral / unconfirmed")


def _format_structure(result: AnalysisResult, signal: dict) -> str:
    structure = result.structure or signal.get("structure", "RANGE")
    bos = BOS_LABELS.get(result.bos or signal.get("bos", "NO_BOS"), "No BOS")
    choch = CHOCH_LABELS.get(result.choch or signal.get("choch", "NO_CHOCH"), "No CHOCH")
    trend = result.trend or signal.get("trend", "SIDEWAYS")
    return _md_escape(f"{trend} · {structure} · {bos} · {choch}")


def _format_liquidity(liquidity: dict | None, direction: str) -> str:
    if not liquidity:
        return _md_escape("No active sweep")
    liq_type = liquidity.get("type", "")
    label = LIQUIDITY_LABELS.get(liq_type, _md_escape(liq_type.replace("_", " ")))
    level = liquidity.get("level")
    if level is not None:
        aligned = (
            (direction == "BUY" and liq_type == "SELL_SIDE_SWEEP")
            or (direction == "SELL" and liq_type == "BUY_SIDE_SWEEP")
        )
        marker = "✅" if aligned else "⚠️"
        return f"{marker} {label} @ {_price(float(level))}"
    return f"⚠️ {label}"


def _format_order_block(orderblock: dict | None, direction: str) -> str:
    if not orderblock:
        return _md_escape("No active order block")
    if direction == "BUY":
        ob = orderblock.get("bullish")
        label = "Bullish OB"
    else:
        ob = orderblock.get("bearish")
        label = "Bearish OB"
    if not ob:
        other = orderblock.get("bearish" if direction == "BUY" else "bullish")
        if other:
            return _md_escape(f"{label} absent · opposite zone active")
        return _md_escape("No aligned order block")
    low, high = float(ob["low"]), float(ob["high"])
    return f"✅ {_md_escape(label)} {_price(low)} \\- {_price(high)}"


def _format_fvg(fvg: dict | None, direction: str) -> str:
    if not fvg:
        return _md_escape("No active FVG")
    fvg_type = fvg.get("type", "")
    aligned = (direction == "BUY" and fvg_type == "BULLISH") or (
        direction == "SELL" and fvg_type == "BEARISH"
    )
    marker = "✅" if aligned else "⚠️"
    bottom = float(fvg.get("bottom", 0))
    top = float(fvg.get("top", 0))
    size = fvg.get("size")
    size_txt = f" \\({_md_escape(str(size))}\\)" if size is not None else ""
    return f"{marker} {_md_escape(fvg_type.title())} {_price(bottom)} \\- {_price(top)}{size_txt}"


def _format_session(signal: dict, result: AnalysisResult) -> str:
    fs = _fs_by_name(signal.get("feature_scores") or [])
    for name in ("Session Strength", "Session"):
        entry = fs.get(name)
        if entry and entry.get("reason"):
            return _md_escape(str(entry["reason"]))

    for gate in signal.get("gates_passed") or []:
        if "session" in gate.lower() or "london" in gate.lower() or "ny" in gate.lower():
            return _md_escape(gate)

    for gate in signal.get("gates_failed") or []:
        if "session" in gate.lower():
            return _md_escape(gate)

    ts = result.df.iloc[-1].get("timestamp")
    if ts is not None and not pd.isna(ts):
        hour = pd.Timestamp(ts).hour
        if 13 <= hour < 16:
            return _md_escape("London/NY overlap (high activity)")
        if 8 <= hour < 13:
            return _md_escape("London session")
        if 16 <= hour < 21:
            return _md_escape("New York session")
        return _md_escape("Asia / off\\-hours")

    hour = datetime.now(timezone.utc).hour
    if 13 <= hour < 16:
        return _md_escape("London/NY overlap (high activity)")
    if 8 <= hour < 13:
        return _md_escape("London session")
    if 16 <= hour < 21:
        return _md_escape("New York session")
    return _md_escape("Asia / off\\-hours")


def _estimate_duration(interval: str, rr: float) -> str:
    minutes = INTERVAL_MINUTES.get(interval, 15)
    low_bars = max(3, int(rr * 2))
    high_bars = max(low_bars + 2, int(rr * 6))
    low_m = low_bars * minutes
    high_m = high_bars * minutes
    return _md_escape(_duration_label(low_m, high_m))


def _duration_label(low_m: int, high_m: int) -> str:
    def fmt(m: int) -> str:
        if m < 60:
            return f"{m}m"
        if m < 1440:
            h = m / 60
            return f"{h:.0f}h" if h == int(h) else f"{h:.1f}h"
        return f"{m / 1440:.1f}d"

    return f"{fmt(low_m)} – {fmt(high_m)}"


def _invalidation_reason(direction: str, risk: dict, result: AnalysisResult) -> str:
    stop = float(risk["stop"])
    entry = float(risk["entry"])
    risk_pct = abs(entry - stop) / entry * 100 if entry else 0
    if direction == "BUY":
        base = f"Close below {_price(stop)} \\({_md_escape(f'{risk_pct:.2f}%')} risk\\)"
        if result.structure == "DOWNTREND":
            return _md_escape("Structure flip bearish · ") + base
        return base
    base = f"Close above {_price(stop)} \\({_md_escape(f'{risk_pct:.2f}%')} risk\\)"
    if result.structure == "UPTREND":
        return _md_escape("Structure flip bullish · ") + base
    return base


def _risk_level(grade: str, confidence: float) -> str:
    if grade == "A+":
        return "Low"
    if grade == "A":
        return "Moderate"
    if grade == "B":
        return "Elevated"
    if confidence >= 85:
        return "Moderate"
    if confidence >= 70:
        return "Elevated"
    return "High"


def _engine_label(setup_type: str) -> str:
    if setup_type == "pro_v2_signal":
        return "AI Trading System PRO V2"
    return "AI Trading System PRO"


def _build_confirmations(
    signal: dict,
    result: AnalysisResult,
    direction: str,
) -> list[tuple[str, bool]]:
    fs = _fs_by_name(signal.get("feature_scores") or [])
    gates = signal.get("gates_passed") or []
    bos = signal.get("bos", result.bos)
    choch = signal.get("choch", result.choch)
    liquidity = _resolve_liquidity(signal, result)
    orderblock = _resolve_orderblock(signal, result)
    fvg = _resolve_fvg(signal, result)
    trend = result.trend or signal.get("trend", "SIDEWAYS")
    htf_bias = (signal.get("htf_bias") or "").lower()

    checks: list[tuple[str, Callable[[], bool]]] = [
        (
            "HTF Bias",
            lambda: (
                (direction == "BUY" and "bullish" in htf_bias)
                or (direction == "SELL" and "bearish" in htf_bias)
                or _names_aligned(fs, ("HTF Bias", "Multi-Timeframe"), direction, 70)
            ),
        ),
        (
            "BOS",
            lambda: (direction == "BUY" and bos == "BULLISH_BOS")
            or (direction == "SELL" and bos == "BEARISH_BOS")
            or _names_aligned(fs, ("Market Structure", "BOS", "Structure Break"), direction, 70),
        ),
        (
            "CHOCH",
            lambda: (direction == "BUY" and choch == "BULLISH_CHOCH")
            or (direction == "SELL" and choch == "BEARISH_CHOCH")
            or _names_aligned(fs, ("CHOCH",), direction, 70),
        ),
        (
            "Liquidity Sweep",
            lambda: (
                (direction == "BUY" and liquidity and liquidity.get("type") == "SELL_SIDE_SWEEP")
                or (direction == "SELL" and liquidity and liquidity.get("type") == "BUY_SIDE_SWEEP")
                or _names_aligned(fs, ("Liquidity Sweep", "Liquidity Sweeps", "Liquidity"), direction, 70)
            ),
        ),
        (
            "Order Block",
            lambda: _names_aligned(
                fs, ("Order Block", "Order Blocks", "POI Return"), direction, 70
            )
            or bool(orderblock),
        ),
        (
            "Fair Value Gap",
            lambda: _names_aligned(fs, ("Fair Value Gap", "Fair Value Gaps"), direction, 70)
            or bool(fvg),
        ),
        (
            "EMA Trend",
            lambda: (direction == "BUY" and trend == "BULLISH")
            or (direction == "SELL" and trend == "BEARISH")
            or _names_aligned(fs, ("EMA Trend", "EMA Stack", "EMA"), direction, 70),
        ),
        (
            "ADX",
            lambda: _gate_passed(gates, "ADX")
            or _names_aligned(fs, ("ADX", "ADX Trend", "Trend Strength"), direction, 70),
        ),
        (
            "RSI",
            lambda: _names_aligned(fs, ("RSI",), direction, 55),
        ),
        (
            "ATR",
            lambda: _gate_passed(gates, "ATR", "Volatility")
            or _names_aligned(fs, ("ATR Volatility", "ATR", "Volatility"), direction, 55),
        ),
        (
            "Volume",
            lambda: _names_aligned(fs, ("Volume", "Volume Profile"), direction, 70),
        ),
    ]

    return [(label, check()) for label, check in checks]


def _compact_checklist(confirmations: list[tuple[str, bool]]) -> list[str]:
    """Two confirmations per line for a tighter mobile layout."""
    short = {
        "HTF Bias": "HTF",
        "Liquidity Sweep": "Liq Sweep",
        "Order Block": "OB",
        "Fair Value Gap": "FVG",
        "EMA Trend": "EMA",
    }
    lines: list[str] = []
    row: list[str] = []
    for label, ok in confirmations:
        tag = short.get(label, label)
        row.append(f"{'✅' if ok else '❌'} {_md_escape(tag)}")
        if len(row) == 2:
            lines.append(" · ".join(row))
            row = []
    if row:
        lines.append(row[0])
    return lines


def _format_signal_reason(signal: dict) -> str:
    """Primary human-readable reason the engine emitted this signal."""
    reasons = signal.get("reasons") or []
    if reasons:
        return _md_escape("; ".join(str(r) for r in reasons[:3]))
    narrative = (signal.get("narrative") or "").strip()
    if narrative:
        return _md_escape(narrative[:200])
    return _md_escape("Multi\\-factor confluence aligned with signal direction")


def _format_intelligence_section(signal: dict) -> list[str]:
    """Multi-source intelligence block — never claims unavailable data."""
    intel = signal.get("intelligence")
    if not intel:
        return []

    def _score_label(val, *, unavailable: str = "N/A") -> str:
        if val is None:
            return unavailable
        if val >= 70:
            return "Strong"
        if val >= 55:
            return "Moderate"
        if val >= 40:
            return "Neutral"
        return "Weak"

    def _sentiment_label(val) -> str:
        if val is None:
            return "Unavailable"
        scaled = (float(val) - 50) / 50.0
        if scaled > 0.15:
            return "Positive"
        if scaled < -0.15:
            return "Negative"
        return "Neutral"

    tech = intel.get("technical_score")
    regime = intel.get("market_regime") or intel.get("btc_trend") or "Unknown"
    news = _sentiment_label(intel.get("news_score"))
    social = _sentiment_label(intel.get("social_score"))
    if intel.get("social_score") is None:
        social = "Unavailable"
    fundamental = _score_label(intel.get("fundamental_score"), unavailable="Unavailable")
    onchain = _score_label(intel.get("onchain_score"), unavailable="Unavailable")
    liquidity = _score_label(intel.get("liquidity_score"))

    reasons = intel.get("key_reasons") or []
    warnings = intel.get("warnings") or []
    unavailable = intel.get("sources_unavailable") or []

    lines = [
        _section("Multi\\-Source Intelligence"),
        f"📊 *Technical* `{_md_escape(f'{tech:.0f}/100' if tech is not None else 'N/A')}`",
        f"🌍 *Market Regime* {_md_escape(str(regime))}",
        f"📰 *News* {_md_escape(news)}",
        f"🐦 *Social/X* {_md_escape(social)}",
        f"🏦 *Fundamental* {_md_escape(fundamental)}",
        f"⛓ *On\\-chain* {_md_escape(onchain)}",
        f"💧 *Liquidity* {_md_escape(liquidity)}",
    ]

    if reasons:
        lines.append("")
        lines.append("*Why:*")
        for r in reasons[:5]:
            lines.append(f"• {_md_escape(str(r)[:100])}")

    if warnings:
        lines.append("")
        lines.append("*Risks:*")
        for w in warnings[:4]:
            lines.append(f"• {_md_escape(str(w)[:100])}")

    if unavailable:
        unavail_short = ", ".join(str(u).split(":")[0] for u in unavailable[:4])
        lines.append("")
        lines.append(f"📡 *Data* {_md_escape(unavail_short)} unavailable")

    freshness = intel.get("data_freshness_minutes")
    if freshness is not None:
        lines.append(f"🕒 *Freshness* `{_md_escape(f'{freshness:.0f}m')}`")

    lines.append("")
    lines.append("⚠️ *SIGNAL ONLY — NO AUTOMATED TRADING*")
    return lines


def _format_premium_signal(
    result: AnalysisResult,
    *,
    timeframe: str | None = None,
    min_confidence: float = 90,
) -> Optional[str]:
    signal = result.signal
    direction = signal.get("signal")
    if direction not in ("BUY", "SELL"):
        return None

    confidence = float(signal.get("confidence", signal.get("confluence", 0)))
    if confidence < min_confidence:
        return None

    risk = result.risk
    if not risk:
        return None

    validation = validate_signal(
        result,
        min_confidence=min_confidence,
        market_price=result.price,
    )
    if not validation.ok:
        return None

    interval = timeframe or DEFAULT_INTERVAL
    tf = format_timeframe(interval)
    symbol = _md_escape(result.symbol)
    grade = str(signal.get("grade") or "—")
    setup_type = signal.get("setup_type", "pro_signal")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    current_price = float(result.price)

    entry = float(risk["entry"])
    stop = float(risk["stop"])
    tp1 = float(risk["tp1"])
    tp2 = float(risk["tp2"])
    tp3 = float(risk["tp3"])
    rr_tp1 = float(risk.get("rr_tp1", compute_rr(entry, stop, tp1)))
    rr_tp2 = float(risk.get("rr_tp2", compute_rr(entry, stop, tp2)))
    rr_tp3 = float(risk.get("rr_tp3", compute_rr(entry, stop, tp3)))

    signal_icon = "🟢" if direction == "BUY" else "🔴"
    side = _md_escape("LONG" if direction == "BUY" else "SHORT")
    signal_label = _md_escape(direction)

    liquidity = _resolve_liquidity(signal, result)
    orderblock = _resolve_orderblock(signal, result)
    fvg = _resolve_fvg(signal, result)

    confirmations = _build_confirmations(signal, result, direction)
    hits = sum(1 for _, ok in confirmations if ok)
    checklist = _compact_checklist(confirmations)

    risk_level = _md_escape(_risk_level(grade, confidence))
    engine = _md_escape(_engine_label(setup_type))
    conf_bar = _confidence_bar(confidence)
    narrative = (signal.get("narrative") or "").strip()

    risk_pct = abs(entry - stop) / entry * 100 if entry else 0
    reward_tp1_pct = abs(tp1 - entry) / entry * 100 if entry else 0
    entry_type = str(risk.get("entry_type") or "market")
    entry_dist = float(risk.get("entry_distance_pct") or abs(current_price - entry) / entry * 100)

    counter_trend_line = ""
    if validation.counter_trend and validation.counter_trend_label:
        counter_trend_line = f"⚠️ *Setup* {_md_escape(validation.counter_trend_label)}"

    lines = [
        f"🚀 *AI TRADING SYSTEM PRO*",
        _divider(26),
        "",
        f"{signal_icon} *{signal_label}* · *{side}* · *{symbol}* · `{_md_escape(tf)}`",
        "",
    ]
    if counter_trend_line:
        lines.append(counter_trend_line)
        lines.append("")
    lines.extend([
        _section("Trade Setup"),
        f"💹 *Current*   {_price(current_price)}",
        f"💰 *Entry*     {_price(entry)} \\({_md_escape(entry_type)} · {_md_escape(f'{entry_dist:.2f}%')} from market\\)",
        f"🛑 *Stop Loss* {_price(stop)} \\({_md_escape(_pct_change(entry, stop))}\\)",
        f"🎯 *TP1*       {_price(tp1)} \\({_md_escape(_pct_change(entry, tp1))}\\)",
        f"🎯 *TP2*       {_price(tp2)} \\({_md_escape(_pct_change(entry, tp2))}\\)",
        f"🎯 *TP3*       {_price(tp3)} \\({_md_escape(_pct_change(entry, tp3))}\\)",
        f"📈 *Risk*      `{_md_escape(f'{risk_pct:.2f}%')}`",
        f"📈 *R:R TP1*   `{_md_escape(f'1:{rr_tp1:.2f}')}` · *TP2* `{_md_escape(f'1:{rr_tp2:.2f}')}` · *TP3* `{_md_escape(f'1:{rr_tp3:.2f}')}`",
        "",
        _section("AI Confidence"),
        f"⭐ *Grade* {_grade_display(grade)}",
        f"🎯 *AI Confidence* *{_md_escape(f'{confidence:.1f}%')}*",
        conf_bar,
        f"📋 *Reason* {_format_signal_reason(signal)}",
        "",
        _section("Market Context"),
        f"🧭 *HTF Bias* {_format_htf_bias(signal)}",
        f"🏛 *Structure* {_format_structure(result, signal)}",
        f"💧 *Liquidity* {_format_liquidity(liquidity, direction)}",
        f"📦 *Order Block* {_format_order_block(orderblock, direction)}",
        f"⚡ *FVG* {_format_fvg(fvg, direction)}",
        f"🕐 *Session* {_format_session(signal, result)}",
        "",
        _section("Confirmations"),
        f"*Score* `{hits}/{len(confirmations)}` aligned",
        *checklist,
        "",
        _section("Trade Plan"),
        f"⏳ *Est\\. Duration* {_estimate_duration(interval, rr_tp1)}",
        f"⚠️ *Invalidation* {_invalidation_reason(direction, risk, result)}",
    ])

    if narrative:
        lines.extend([
            f"📝 *Narrative* {_md_escape(narrative[:180])}",
        ])

    intel_lines = _format_intelligence_section(signal)
    if intel_lines:
        lines.extend([""] + intel_lines)

    lines.extend([
        "",
        _divider(26),
        f"⚠️ *Risk Level* {risk_level}",
        f"⏱ *Signal Time \\(UTC\\)* {_md_escape(timestamp)}",
        f"🤖 *Generated by {engine}*",
    ])

    return "\n".join(lines)


def format_signal_message(
    result: AnalysisResult,
    *,
    timeframe: str | None = None,
    min_confidence: float = 90,
) -> Optional[str]:
    """Format a premium institutional signal alert for Telegram."""
    return _format_premium_signal(
        result,
        timeframe=timeframe,
        min_confidence=min_confidence,
    )


def format_live_signal_message(
    result: AnalysisResult,
    *,
    timeframe: str | None = None,
    min_confidence: float = 90,
) -> Optional[str]:
    """Format a 24/7 service alert — same premium layout as format_signal_message."""
    return _format_premium_signal(
        result,
        timeframe=timeframe,
        min_confidence=min_confidence,
    )


def format_service_startup_message(
    *,
    symbol_count: int,
    scan_interval_seconds: int,
    min_confidence: float,
) -> str:
    """MarkdownV2-safe startup notification for the 24/7 signal service."""
    return (
        "🚀 *AI Signal Service Online*\n\n"
        f"Scanning `{symbol_count}` symbols every "
        f"`{scan_interval_seconds}s`\\.\n"
        f"Alerts fire at confidence \\>\\= `{min_confidence:.0f}`\\."
    )


def format_test_message() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    bar = _confidence_bar(100.0)
    return (
        "🚀 *AI TRADING SYSTEM PRO*\n"
        f"{_divider(26)}\n"
        "\n"
        "✅ *Telegram Integration Active*\n"
        "\n"
        "*▸ AI CONFIDENCE*\n"
        f"{_divider()}\n"
        "🎯 *AI Confidence* *100\\.0%*\n"
        f"{bar}\n"
        "\n"
        "Institutional signal formatting is live\\. "
        "High\\-confidence alerts will arrive with full trade context\\.\n"
        "\n"
        f"{_divider(26)}\n"
        f"⏱ *Signal Time \\(UTC\\)* {_md_escape(timestamp)}\n"
        "🤖 *Generated by AI Trading System PRO V2*"
    )
