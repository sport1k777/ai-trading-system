"""Walk-forward backtester for Signal Engine PRO V2."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from app.analysis.market_context import MarketContextBuilder
from app.analysis.pro_v2.engine import SignalEngineProV2
from app.config import (
    BACKTEST_MAX_HOLD_BARS,
    BACKTEST_WARMUP_BARS,
    MIN_BARS_BETWEEN_TRADES,
)
from app.risk.risk_manager import RiskManager

logger = logging.getLogger(__name__)


def run_pro_v2_backtest(
    df: pd.DataFrame,
    *,
    symbol: str = "BTCUSDT",
    interval: str = "15",
    warmup: int = BACKTEST_WARMUP_BARS,
    max_hold: int = BACKTEST_MAX_HOLD_BARS,
    min_spacing: int = MIN_BARS_BETWEEN_TRADES,
) -> dict:
    trades: list[dict] = []
    last_trade_bar = -min_spacing
    equity_r = 0.0

    for i in range(warmup, len(df) - 1):
        if i - last_trade_bar < min_spacing:
            continue

        slice_df = df.iloc[: i + 1].copy()
        ctx = MarketContextBuilder.build(
            slice_df,
            symbol=symbol,
            interval=interval,
            indicators_calculated=False,
        )
        signal = SignalEngineProV2.generate(
            ctx.df,
            indicators_calculated=True,
            context=ctx,
            symbol=symbol,
            interval=interval,
        )

        if signal["signal"] not in ("BUY", "SELL"):
            continue

        entry_bar = i
        entry = float(slice_df.iloc[-1]["close"])
        atr = float(slice_df.iloc[-1]["atr"])
        swing_lows = signal.get("swing_lows") or []
        swing_highs = signal.get("swing_highs") or []
        sl = swing_lows[-1]["price"] if swing_lows else None
        sh = swing_highs[-1]["price"] if swing_highs else None

        future = df.iloc[i + 1 : i + 1 + max_hold]
        if future.empty:
            continue

        outcome = RiskManager.simulate_trade(
            signal["signal"],
            entry,
            atr,
            future,
            swing_low=sl,
            swing_high=sh,
            setup_type=signal.get("setup_type", "pro_v2_signal"),
        )
        last_trade_bar = i
        pnl = outcome["pnl_r"]
        equity_r += pnl
        trades.append(
            {
                "bar": entry_bar,
                "signal": signal["signal"],
                "grade": signal.get("grade", "?"),
                "confidence": signal.get("confidence", 0),
                "result": outcome["result"],
                "pnl_r": pnl,
            }
        )

    wins = [t for t in trades if t["pnl_r"] > 0]
    losses = [t for t in trades if t["pnl_r"] < 0]
    gross_win = sum(t["pnl_r"] for t in wins)
    gross_loss = abs(sum(t["pnl_r"] for t in losses))
    pf = gross_win / gross_loss if gross_loss else float("inf") if gross_win else 0.0

    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "profit_factor": round(pf, 2),
        "total_r": round(equity_r, 2),
        "avg_r": round(equity_r / len(trades), 3) if trades else 0.0,
        "trade_list": trades,
    }


def save_report(report: dict, path: str | Path) -> None:
    import json
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in report.items() if k != "trade_list"}
    with path.open("w") as f:
        json.dump(payload, f, indent=2)
