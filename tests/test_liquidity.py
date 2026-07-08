import pandas as pd

from app.analysis.liquidity import LiquidityAnalyzer


def test_buy_side_sweep_detected():
    df = pd.DataFrame(
        {
            "high": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
                     110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
                     120, 121, 122, 123, 124, 125],
            "low": [99, 100, 101, 102, 103, 104, 105, 106, 107, 108,
                    109, 110, 111, 112, 113, 114, 115, 116, 117, 118,
                    119, 120, 121, 122, 123, 124],
            "close": [99.5, 100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5,
                      107.5, 108.5, 109.5, 110.5, 111.5, 112.5, 113.5, 114.5,
                      115.5, 116.5, 117.5, 118.5, 119.5, 120.5, 121.5, 122.5,
                      123.0, 122.0],
        }
    )
    df.iloc[-1, df.columns.get_loc("high")] = 125.0
    df.iloc[-1, df.columns.get_loc("close")] = 122.0

    result = LiquidityAnalyzer.analyze(df, lookback=20)
    assert result is not None
    assert result["type"] == "BUY_SIDE_SWEEP"
