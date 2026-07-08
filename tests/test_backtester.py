import pandas as pd

from app.analysis.signal_generator import SignalGenerator
from app.indicators.signals import SignalIndicators
from app.risk.risk_manager import RiskManager


def test_backtest_loop_logic(sample_ohlcv):
    """Verify walk-forward produces trade outcomes without API calls."""
    df = SignalIndicators.calculate(sample_ohlcv)
    trades = []

    for i in range(200, len(df) - 10):
        history = df.iloc[: i + 1].copy()
        signal = SignalGenerator.generate(history, indicators_calculated=True)

        if signal["signal"] == "WAIT":
            continue

        entry = float(history.iloc[-1]["close"])
        atr = float(history.iloc[-1]["atr"])
        if atr <= 0:
            continue

        future = df.iloc[i + 1 : i + 6]
        outcome = RiskManager.simulate_trade(signal["signal"], entry, atr, future)
        trades.append(outcome)

    for trade in trades:
        assert trade["result"] in ("WIN", "LOSS", "TIMEOUT")
        assert "pnl_r" in trade
