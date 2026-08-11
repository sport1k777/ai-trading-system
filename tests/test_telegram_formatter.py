"""Tests for Telegram MarkdownV2 formatting."""

from __future__ import annotations

from app.telegram.formatter import (
    _md_escape,
    format_service_startup_message,
    format_test_message,
)


def test_md_escape_special_characters():
    assert _md_escape("1.5%") == "1\\.5%"
    assert _md_escape("a_b") == "a\\_b"
    assert _md_escape("test (live)") == "test \\(live\\)"


def test_format_test_message_is_markdownv2_safe():
    msg = format_test_message()
    assert "100\\.0%" in msg
    assert "High\\-confidence" in msg
    assert "Telegram Integration Active" in msg


def test_format_signal_message_escapes_confidence_pct():
    """Regression: confidence decimals must be MarkdownV2-escaped (81.2% -> 81\\.2%)."""
    from app.risk.signal_levels import compute_rr, finalize_risk_levels
    from app.telegram.formatter import _format_premium_signal
    from types import SimpleNamespace

    class Result:
        symbol = "SOLUSDT"
        trend = "BULLISH"
        structure = "UPTREND"
        bos = "BULLISH_BOS"
        choch = "NO_CHOCH"
        liquidity = {"type": "SELL_SIDE_SWEEP", "level": 75.4}
        order_block = {"bullish": {"low": 76.0, "high": 77.0}}
        fvg = {"type": "BULLISH", "bottom": 76.5, "top": 76.6, "size": 0.1}
        price = 76.5

        df = __import__("pandas").DataFrame([{
            "close": 76.5,
            "timestamp": "2026-07-13",
            "atr": 0.5,
            "adx": 25.0,
            "ema20": 76.8,
            "ema50": 76.2,
            "rsi": 55.0,
            "volume_ratio": 1.1,
        }])
        signal = {
            "signal": "BUY",
            "confidence": 81.2,
            "grade": "A",
            "feature_scores": [],
            "setup_type": "pro_signal",
            "reasons": ["Bullish BOS + sell-side liquidity sweep at POI"],
            "orderblock": {"bullish": {"low": 76.0, "high": 77.0}},
            "htf_bias": "HTF bullish bias (UPTREND, BULLISH_BOS)",
            "bos": "BULLISH_BOS",
            "choch": "NO_CHOCH",
            "liquidity": {"type": "SELL_SIDE_SWEEP", "level": 75.4},
        }
        risk = finalize_risk_levels("BUY", 76.6, 75.0, 79.0, 80.6, 82.2)
        risk["entry_type"] = "limit"
        risk["entry_distance_pct"] = 0.12

    r = Result()
    msg = _format_premium_signal(r, min_confidence=80)
    assert msg is not None
    assert "81\\.2%" in msg
    assert "*Reason*" in msg
    assert "Bullish BOS" in msg
    assert "`79.0000`" in msg
    assert "`80.6000`" in msg
    assert "`82.2000`" in msg
    rr = compute_rr(r.risk["entry"], r.risk["stop"], r.risk["tp1"])
    assert f"1:{rr:.2f}".replace(".", "\\.") in msg or "R:R TP1" in msg
    msg = format_service_startup_message(
        symbol_count=5,
        scan_interval_seconds=60,
        min_confidence=90.0,
    )
    assert "`5`" in msg
    assert "`60s`\\." in msg
    assert "\\>\\= `90`" in msg
