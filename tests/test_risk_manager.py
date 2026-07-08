import pandas as pd

from app.risk.risk_manager import RiskManager


def test_risk_manager_buy_levels():
    risk = RiskManager.calculate(100.0, 2.0, "BUY", setup_type="pullback")
    assert risk is not None
    assert risk["entry"] == 100.0
    assert risk["stop"] == 98.0
    assert risk["tp1"] == 104.0
    assert risk["rr"] == 2.0


def test_risk_manager_returns_none_for_wait():
    assert RiskManager.calculate(100.0, 2.0, "WAIT") is None


def test_risk_manager_returns_none_for_zero_atr():
    assert RiskManager.calculate(100.0, 0.0, "BUY") is None


def test_momentum_wider_stop():
    risk = RiskManager.calculate(100.0, 2.0, "SELL", setup_type="momentum")
    assert risk["stop"] == 102.4


def test_simulate_trade_buy_hits_stop_first():
    future = pd.DataFrame({"high": [101.0, 100.5], "low": [97.0, 99.0], "close": [99.0, 99.5]})
    outcome = RiskManager.simulate_trade("BUY", 100.0, 2.0, future, setup_type="pullback")
    assert outcome["result"] == "LOSS"
    assert outcome["pnl_r"] == -1.0


def test_simulate_trade_buy_hits_tp():
    future = pd.DataFrame({"high": [105.0, 107.0], "low": [99.5, 100.0], "close": [104.0, 106.0]})
    outcome = RiskManager.simulate_trade("BUY", 100.0, 2.0, future, setup_type="pullback")
    assert outcome["result"] == "WIN"
    assert outcome["pnl_r"] == 2.0


def test_simulate_trade_mean_reversion_tp():
    future = pd.DataFrame({"high": [102.0, 103.0], "low": [99.0, 100.0], "close": [101.0, 102.0]})
    outcome = RiskManager.simulate_trade("BUY", 100.0, 2.0, future, tp_price=103.0, setup_type="mean_reversion")
    assert outcome["result"] == "WIN"
    assert outcome["pnl_r"] > 0
