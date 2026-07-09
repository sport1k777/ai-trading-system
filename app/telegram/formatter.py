"""Premium Telegram message formatting for AI trading signals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from app.config import DEFAULT_INTERVAL

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

TREND_LABELS = {
    "BULLISH": ("📈", "Bullish"),
    "BEARISH": ("📉", "Bearish"),
    "SIDEWAYS": ("↔️", "Sideways / Range"),
}

REASON_CATEGORIES = (
    ("EMA", "EMA"),
    ("RSI", "RSI"),
    ("ADX", "ADX"),
    ("Volume", "Volume"),
    ("Market Structure", "Market Structure"),
    ("Order Blocks", "Order Block"),
    ("Fair Value Gaps", "Fair Value Gap"),
    ("Liquidity Sweeps", "Liquidity"),
    ("Multi-Timeframe", "Multi\\-timeframe confirmation"),
)


def format_timeframe(interval: str) -> str:
    return INTERVAL_LABELS.get(interval, interval)


def _md_escape(text: str) -> str:
    """Escape text for Telegram MarkdownV2 outside of code spans."""
    for char in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(char, f"\\{char}")
    return text


def _price(value: float) -> str:
    """Format price inside a MarkdownV2 code span."""
    if value >= 1000:
        formatted = f"{value:,.2f}"
    elif value >= 1:
        formatted = f"{value:,.4f}"
    else:
        formatted = f"{value:,.6f}"
    return f"`{formatted}`"


def _confidence_bar(confidence: float) -> str:
    filled = min(10, max(0, int(round(confidence / 10))))
    return "🟩" * filled + "⬜" * (10 - filled)


def _trend_line(trend: str) -> str:
    icon, label = TREND_LABELS.get(trend.upper(), ("📊", trend.title()))
    return f"{icon} {_md_escape(label)}"


def _feature_reason_lines(
    feature_scores: list[dict],
    direction: str,
) -> list[str]:
    by_name = {fs["name"]: fs for fs in feature_scores}
    lines: list[str] = []

    for feature_name, display_name in REASON_CATEGORIES:
        fs = by_name.get(feature_name)
        if not fs:
            lines.append(f"• {_md_escape(display_name)}: _Neutral_")
            continue

        score = fs["buy_score"] if direction == "BUY" else fs["sell_score"]
        reason = fs.get("reason", "No data")

        if score >= 70:
            prefix = "✅"
        elif score >= 55:
            prefix = "🟡"
        else:
            prefix = "⚪"

        lines.append(
            f"{prefix} *{_md_escape(display_name)}*: {_md_escape(reason)}"
        )

    return lines


def format_signal_message(
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

    tf = format_timeframe(timeframe or DEFAULT_INTERVAL)
    symbol = _md_escape(result.symbol)
    trend = result.trend or signal.get("trend", "UNKNOWN")

    if direction == "BUY":
        header = "🟢 *BUY SIGNAL*"
        action_icon = "🟢"
    else:
        header = "🔴 *SELL SIGNAL*"
        action_icon = "🔴"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    feature_scores = signal.get("feature_scores") or []
    reason_lines = _feature_reason_lines(feature_scores, direction)

    lines = [
        "⚡ *AI TRADING SIGNAL*",
        header,
        "",
        f"{action_icon} *{_md_escape(direction)}*  ·  *{symbol}*  ·  *{_md_escape(tf)}*",
        f"🕐 {_md_escape(timestamp)}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "💰 *Trade Setup*",
        f"Entry Price: {_price(float(risk['entry']))}",
        f"Stop Loss: {_price(float(risk['stop']))}",
        "",
        "🎯 *Take Profits*",
        f"TP1: {_price(float(risk['tp1']))}",
        f"TP2: {_price(float(risk['tp2']))}",
        f"TP3: {_price(float(risk['tp3']))}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"⚖️ *Risk / Reward:* `1:{float(risk['rr']):.2f}`",
        f"🧠 *Confidence:* *{confidence:.1f}/100*",
        _confidence_bar(confidence),
        f"📊 *Market Trend:* {_trend_line(trend)}",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "✅ *Reasons:*",
        *reason_lines,
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        "_Premium signal · AI Signal Engine_",
    ]

    return "\n".join(lines)


def format_live_signal_message(
    result: AnalysisResult,
    *,
    timeframe: str | None = None,
    min_confidence: float = 90,
) -> Optional[str]:
    """Format a 24/7 service alert with LONG/SHORT labels."""
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

    side = "LONG" if direction == "BUY" else "SHORT"
    side_icon = "🟢" if direction == "BUY" else "🔴"
    tf = format_timeframe(timeframe or DEFAULT_INTERVAL)
    symbol = _md_escape(result.symbol)
    trend = result.trend or signal.get("trend", "UNKNOWN")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    feature_scores = signal.get("feature_scores") or []
    reason_lines = _feature_reason_lines(feature_scores, direction)

    lines = [
        "⚡ *AI LIVE SIGNAL*",
        "",
        f"📈 *Symbol:* *{symbol}* \\({_md_escape(tf)}\\)",
        f"{side_icon} *{side}*",
        "",
        f"💰 *Entry:* {_price(float(risk['entry']))}",
        f"🛑 *Stop Loss:* {_price(float(risk['stop']))}",
        f"🎯 *TP1:* {_price(float(risk['tp1']))}",
        f"🎯 *TP2:* {_price(float(risk['tp2']))}",
        f"🎯 *TP3:* {_price(float(risk['tp3']))}",
        "",
        f"📊 *Risk/Reward:* `1:{float(risk['rr']):.2f}`",
        f"🤖 *Confidence:* *{confidence:.1f}/100*",
        f"🏆 *Grade:* *{_md_escape(str(signal.get('grade', 'N/A')))}*",
        f"📈 *Trend:* {_trend_line(trend)}",
        "",
        "📝 *Reasons:*",
        *reason_lines,
        "",
        f"🕒 *Time \\(UTC\\):* {_md_escape(timestamp)}",
    ]

    return "\n".join(lines)


def format_test_message() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "⚡ *AI TRADING SYSTEM*\n"
        "\n"
        "✅ *Telegram Integration Active*\n"
        "\n"
        f"🕐 {_md_escape(timestamp)}\n"
        "\n"
        "High\\-confidence signals \\(≥90\\) will be delivered automatically "
        "with premium formatting when `app.engine` generates a trade setup\\.\n"
        "\n"
        "_Stay disciplined\\. Manage your risk\\._"
    )
