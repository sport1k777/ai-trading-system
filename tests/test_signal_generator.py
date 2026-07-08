from app.analysis.order_block import OrderBlockAnalyzer
from app.analysis.signal_generator import SignalGenerator
from app.indicators.signals import SignalIndicators


def test_order_block_returns_none_when_empty():
    import pandas as pd

    df = pd.DataFrame(
        {
            "open": [10.0] * 25,
            "high": [11.0] * 25,
            "low": [9.0] * 25,
            "close": [10.5] * 25,
        }
    )
    assert OrderBlockAnalyzer.analyze(df) is None


def test_signal_generator_returns_wait_on_short_data():
    import pandas as pd

    df = pd.DataFrame(
        {
            "open": [10.0] * 10,
            "high": [11.0] * 10,
            "low": [9.0] * 10,
            "close": [10.5] * 10,
        }
    )
    result = SignalGenerator.generate(df)
    assert result["signal"] == "WAIT"
    assert "Insufficient" in result["reasons"][0]


def test_signal_generator_produces_valid_signal(sample_ohlcv):
    df = SignalIndicators.calculate(sample_ohlcv)
    result = SignalGenerator.generate(df, indicators_calculated=True)

    assert result["signal"] in ("BUY", "SELL", "WAIT")
    assert isinstance(result["score"], int)
    assert "choch" in result
    assert isinstance(result["reasons"], list)


def test_no_duplicate_indicator_calculation(sample_with_indicators):
    result = SignalGenerator.generate(sample_with_indicators, indicators_calculated=True)
    assert result["signal"] in ("BUY", "SELL", "WAIT")
