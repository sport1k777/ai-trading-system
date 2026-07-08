import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """250-bar synthetic uptrend with enough history for EMA200."""
    n = 250
    rng = np.random.default_rng(42)

    base = np.linspace(100, 130, n)
    noise = rng.normal(0, 0.3, n)

    close = base + noise
    open_ = close - rng.uniform(-0.5, 0.5, n)
    high = np.maximum(open_, close) + rng.uniform(0.1, 1.0, n)
    low = np.minimum(open_, close) - rng.uniform(0.1, 1.0, n)
    volume = rng.uniform(100, 1000, n)

    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="15min"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "turnover": volume * close,
        }
    )


@pytest.fixture
def sample_with_indicators(sample_ohlcv):
    from app.indicators.signals import SignalIndicators

    return SignalIndicators.calculate(sample_ohlcv)
