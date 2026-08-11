"""
Auto-calibrate signal filters (threshold, conf_gap) for the current dataset.
Preserves learned feature weights — only adjusts entry filters.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.analysis.feature_engine import CONFIG_PATH, WEIGHTS_PATH, load_config, save_model, load_weights
from app.config import BACKTEST_MAX_HOLD_BARS, BACKTEST_WARMUP_BARS, MIN_BARS_BETWEEN_TRADES
from app.risk.risk_manager import RiskManager

MIN_TRADES_SHORT = 5   # minimum for ~1000 bar backtest
MIN_TRADES_LONG = 15   # minimum for full history
MIN_PF = 1.05
MIN_THRESHOLD = 90.0   # AI engine requirement: confidence > 90


def _simulate(
    df: pd.DataFrame,
    threshold: float,
    conf_gap: float,
    stop_mult: float,
    tp_r: float,
) -> list[dict]:
    buy_conf = df["buy_confidence"].values
    sell_conf = df["sell_confidence"].values
    opens = df["open"].values
    atrs = df["atr"].values
    swing_sl = df["swing_sl"].values
    swing_sh = df["swing_sh"].values
    n = len(df)

    trades: list[dict] = []
    last_trade = -MIN_BARS_BETWEEN_TRADES
    end = n - BACKTEST_MAX_HOLD_BARS - 1

    orig = RiskManager.SETUP_PARAMS.get("ai_signal", {}).copy()
    RiskManager.SETUP_PARAMS["ai_signal"] = {"stop_mult": stop_mult, "tp_r": tp_r}

    try:
        for i in range(BACKTEST_WARMUP_BARS, end):
            if i - last_trade < MIN_BARS_BETWEEN_TRADES:
                continue

            bc, sc = buy_conf[i], sell_conf[i]
            if bc >= threshold and bc > sc + conf_gap:
                direction = "BUY"
            elif sc >= threshold and sc > bc + conf_gap:
                direction = "SELL"
            else:
                continue

            entry_idx = i + 1
            entry, atr = float(opens[entry_idx]), float(atrs[i])
            if atr <= 0:
                continue

            sl = float(swing_sl[i]) if not np.isnan(swing_sl[i]) else None
            sh = float(swing_sh[i]) if not np.isnan(swing_sh[i]) else None
            future = df.iloc[entry_idx + 1 : entry_idx + 1 + BACKTEST_MAX_HOLD_BARS]
            if future.empty:
                continue

            outcome = RiskManager.simulate_trade(
                direction, entry, atr, future,
                swing_low=sl if direction == "BUY" else None,
                swing_high=sh if direction == "SELL" else None,
                setup_type="ai_signal",
            )
            trades.append({
                "result": outcome["result"],
                "pnl_r": outcome["pnl_r"],
                "signal": direction,
            })
            last_trade = i
    finally:
        if orig:
            RiskManager.SETUP_PARAMS["ai_signal"] = orig

    return trades


def _metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"total_trades": 0, "win_rate": 0, "profit_factor": 0,
                "net_profit_r": 0, "max_drawdown_r": 999, "avg_rr": 0}

    r = np.array([t["pnl_r"] for t in trades])
    wins = [t for t in trades if t["result"] == "WIN"]
    gp = r[r > 0].sum()
    gl = abs(r[r < 0].sum())
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    max_dd = float((peak - equity).max())
    avg_rr = float(np.mean([t["pnl_r"] for t in wins])) if wins else 0.0

    return {
        "total_trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 2),
        "profit_factor": round(gp / gl, 2) if gl > 0 else float("inf"),
        "net_profit_r": round(float(r.sum()), 2),
        "max_drawdown_r": round(max_dd, 2),
        "avg_rr": round(avg_rr, 2),
    }


def diagnose(df: pd.DataFrame) -> dict:
    """Report why signals may be blocked."""
    cfg = load_config()
    bc = df["buy_confidence"].values
    sc = df["sell_confidence"].values
    thresh = cfg.get("threshold", 90)
    gap = cfg.get("conf_gap", 8)

    end = len(df) - BACKTEST_MAX_HOLD_BARS - 1
    active = slice(BACKTEST_WARMUP_BARS, end)
    bc_a, sc_a = bc[active], sc[active]

    raw_buy = int(((bc_a >= thresh) & (bc_a > sc_a + gap)).sum())
    raw_sell = int(((sc_a >= thresh) & (sc_a > bc_a + gap)).sum())

    return {
        "bars": len(df),
        "threshold": thresh,
        "conf_gap": gap,
        "calibration": cfg.get("calibration", 0.57),
        "max_buy_conf": round(float(bc_a.max()), 1),
        "max_sell_conf": round(float(sc_a.max()), 1),
        "raw_buy_signals": raw_buy,
        "raw_sell_signals": raw_sell,
        "bars_buy_above_90": int((bc_a >= 90).sum()),
        "bars_sell_above_90": int((sc_a >= 90).sum()),
    }


PRODUCTION_MODEL = Path(".cache/production/production_model.json")


def calibrate(df: pd.DataFrame, *, min_trades: int | None = None) -> dict:
    """
    Find the strictest profitable filter settings that produce enough trades.
    Skips adjustment when a production model is deployed (short-sample only).
    """
    if PRODUCTION_MODEL.exists() and len(df) < 3000:
        cfg = load_config()
        diag = diagnose(df)
        current_trades = _simulate(
            df, cfg.get("threshold", 90), cfg.get("conf_gap", 8),
            cfg.get("stop_mult", 0.9), cfg.get("tp_r", 2.0),
        )
        return {
            "adjusted": False, "config": cfg,
            "metrics": _metrics(current_trades),
            "diagnosis": diag,
            "note": "Production model active — filters not auto-adjusted on short samples",
        }
    cfg = load_config()
    weights = load_weights()
    stop_mult = cfg.get("stop_mult", 0.9)
    tp_r = cfg.get("tp_r", 2.2)

    if min_trades is None:
        min_trades = MIN_TRADES_SHORT if len(df) < 3000 else MIN_TRADES_LONG

    diag = diagnose(df)
    current_trades = _simulate(
        df, cfg.get("threshold", 90), cfg.get("conf_gap", 8), stop_mult, tp_r,
    )
    current_m = _metrics(current_trades)

    if current_m["total_trades"] >= min_trades and current_m["profit_factor"] >= MIN_PF:
        return {"adjusted": False, "config": cfg, "metrics": current_m, "diagnosis": diag}

    # Also recalibrate when zero trades regardless of saved config
    if current_m["total_trades"] == 0:
        min_trades = max(3, min_trades // 2)

    best_cfg = None
    best_m = None
    best_score = -1e9

    # Search: prefer higher threshold (quality) with lower conf_gap if needed
    for threshold in np.arange(98, MIN_THRESHOLD - 0.1, -0.5):
        for conf_gap in [6, 8, 10, 12, 14, 16, 18]:
            trades = _simulate(df, threshold, conf_gap, stop_mult, tp_r)
            m = _metrics(trades)
            if m["total_trades"] < min_trades:
                continue
            if m["profit_factor"] < MIN_PF or m["net_profit_r"] <= 0:
                continue

            score = (
                m["profit_factor"] * 40
                + m["win_rate"] * 2
                + m["net_profit_r"]
                + threshold * 0.5          # favour higher threshold
                - conf_gap * 0.3             # favour tighter gap when possible
                - m["max_drawdown_r"] * 0.5
            )
            if score > best_score:
                best_score = score
                best_cfg = {
                    **cfg,
                    "threshold": round(float(threshold), 1),
                    "conf_gap": float(conf_gap),
                }
                best_m = m

    if best_cfg is None:
        # Relax slightly: allow PF >= 1.0 for short samples
        for threshold in np.arange(97, MIN_THRESHOLD - 0.1, -0.5):
            for conf_gap in [6, 8, 10, 12]:
                trades = _simulate(df, threshold, conf_gap, stop_mult, tp_r)
                m = _metrics(trades)
                if m["total_trades"] < max(3, min_trades // 2):
                    continue
                if m["profit_factor"] < 1.0 or m["net_profit_r"] <= 0:
                    continue
                score = m["profit_factor"] * 30 + m["net_profit_r"] + threshold * 0.3
                if score > best_score:
                    best_score = score
                    best_cfg = {**cfg, "threshold": round(float(threshold), 1), "conf_gap": float(conf_gap)}
                    best_m = m

    if best_cfg is None:
        return {
            "adjusted": False,
            "config": cfg,
            "metrics": current_m,
            "diagnosis": diag,
            "error": "Could not find profitable filter settings for this dataset",
        }

    save_model(weights, best_cfg)
    return {"adjusted": True, "config": best_cfg, "metrics": best_m, "diagnosis": diag,
            "previous": {"threshold": cfg.get("threshold"), "conf_gap": cfg.get("conf_gap")}}


class FilterCalibrator:
    calibrate = staticmethod(calibrate)
    diagnose = staticmethod(diagnose)
