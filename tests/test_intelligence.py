"""Tests for multi-source intelligence architecture."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.intelligence.aggregator import IntelligenceAggregator
from app.intelligence.freshness import freshness_weight, is_stale_for_signals
from app.intelligence.market_regime import GlobalMarketRegime
from app.intelligence.models import IntelligenceItem, ProviderResult, ReliabilityTier, SymbolIntelligence
from app.intelligence.providers.social_twitter import SocialTwitterProvider
from app.intelligence.scoring import score_candidate
from app.pipeline import AnalysisResult


def _make_result(
    symbol: str = "SOLUSDT",
    direction: str = "BUY",
    confidence: float = 80.0,
) -> AnalysisResult:
    n = 50
    df = pd.DataFrame(
        {
            "close": [100.0] * n,
            "atr": [2.0] * n,
            "adx": [28.0] * n,
            "rsi": [55.0] * n,
            "ema20": [101.0] * n,
            "ema50": [99.0] * n,
            "volume_ratio": [1.3] * n,
        }
    )
    return AnalysisResult(
        symbol=symbol,
        df=df,
        signal={"signal": direction, "confidence": confidence},
        risk={
            "entry": 100.0,
            "stop": 98.0,
            "tp1": 103.0,
            "tp2": 105.0,
            "tp3": 108.0,
            "rr_tp1": 1.5,
            "rr_tp2": 2.5,
            "rr_tp3": 4.0,
        },
        trend="BULLISH",
        structure="UPTREND",
        bos="BULLISH_BOS",
        choch="NO_CHOCH",
        liquidity={"type": "SELL_SIDE_SWEEP"},
        order_block={"bullish": {"low": 99.5, "high": 100.5}},
        fvg=None,
        swing_highs=[],
        swing_lows=[],
    )


def test_freshness_decay():
    assert freshness_weight(0) == pytest.approx(1.0, rel=0.01)
    assert freshness_weight(120, half_life_minutes=120) == pytest.approx(0.5, rel=0.05)
    assert is_stale_for_signals(47 * 60) is False
    assert is_stale_for_signals(49 * 60) is True


def test_social_provider_unavailable_without_credentials():
    with patch("app.intelligence.providers.social_twitter.TWITTER_BEARER_TOKEN", ""):
        provider = SocialTwitterProvider()
        result = provider.fetch(["BTCUSDT"])
        assert result.available is False
        assert "unavailable" in result.error.lower()


def test_scoring_blocks_negative_news_on_long():
    result = _make_result(direction="BUY")
    intel = SymbolIntelligence(symbol="SOLUSDT", news_score=-0.8)
    regime = GlobalMarketRegime(
        btc_trend="BULLISH",
        btc_structure="UPTREND",
        btc_volatility="NORMAL",
        risk_mode="RISK_ON",
        altcoin_long_favorable=True,
        altcoin_short_favorable=False,
        summary="BTC bullish",
    )
    with patch("app.intelligence.scoring.INTELLIGENCE_BLOCK_NEGATIVE_NEWS", True):
        scores = score_candidate(result, intel, regime)
    assert scores.blocked
    assert any("news" in b.lower() for b in scores.blockers)


def test_scoring_never_claims_social_without_data():
    result = _make_result()
    intel = SymbolIntelligence(symbol="SOLUSDT", social_score=None)
    regime = GlobalMarketRegime(
        btc_trend="BULLISH",
        btc_structure="UPTREND",
        btc_volatility="NORMAL",
        risk_mode="RISK_ON",
        altcoin_long_favorable=True,
        altcoin_short_favorable=False,
        summary="BTC bullish",
    )
    scores = score_candidate(result, intel, regime)
    assert any("Social/X: unavailable" in r for r in scores.key_reasons)


def test_scoring_blocks_long_when_btc_regime_unfavorable():
    result = _make_result(symbol="ETHUSDT", direction="BUY")
    intel = SymbolIntelligence(symbol="ETHUSDT")
    regime = GlobalMarketRegime(
        btc_trend="BEARISH",
        btc_structure="DOWNTREND",
        btc_volatility="HIGH",
        risk_mode="RISK_OFF",
        altcoin_long_favorable=False,
        altcoin_short_favorable=True,
        summary="BTC bearish risk-off",
    )
    scores = score_candidate(result, intel, regime)
    assert scores.blocked
    assert any("BTC regime" in b for b in scores.blockers)


def test_aggregator_isolates_provider_failure():
    good = MagicMock()
    good.name = "good_provider"
    good.fetch.return_value = ProviderResult(
        "good_provider",
        True,
        items=[
            IntelligenceItem(
                source="test",
                category="news",
                headline="SOL partnership",
                symbol="SOLUSDT",
                sentiment=0.5,
                relevance=0.9,
                reliability=ReliabilityTier.REPUTABLE,
                published_at=datetime.now(timezone.utc),
            )
        ],
    )
    bad = MagicMock()
    bad.name = "bad_provider"
    bad.fetch.side_effect = RuntimeError("API down")

    agg = IntelligenceAggregator(providers=[good, bad])
    with patch("app.intelligence.aggregator.INTELLIGENCE_ENABLED", True):
        results = agg.fetch_batch(["SOLUSDT"], force_refresh=True)

    intel = results["SOLUSDT"]
    assert "good_provider" in intel.available_sources
    assert intel.news_score is not None


def test_validate_intelligence_blockers():
    from app.validation.signal_validator import _validate_intelligence_blockers

    signal = {"intelligence": {"blockers": ["Blocking negative news contradicts LONG setup"]}}
    errors = _validate_intelligence_blockers(signal)
    assert len(errors) == 1
    assert "Intelligence" in errors[0]


def test_validate_min_reward_rejects_tiny_tp():
    from app.validation.signal_validator import _validate_min_reward

    ok, msg = _validate_min_reward("BUY", 100.0, 100.01, 2.0)
    assert ok is False
    assert "TP1 reward" in msg
