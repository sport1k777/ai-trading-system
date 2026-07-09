"""
Batch feature precomputation — vectorized additive scoring for fast backtesting.
Supports parameterized weights and contribution caching for self-learning optimization.
Live pipeline uses AISignalEngine.generate() for full per-feature reasons.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import AI_FEATURE_WEIGHTS
from app.indicators.extended import ExtendedIndicators
from app.indicators.signals import SignalIndicators

WEIGHTS_PATH = Path(".cache/ai_weights.json")
CONFIG_PATH = Path(".cache/ai_config.json")

DEFAULT_FEATURE_WEIGHTS = {
    "ema": 8.0,
    "rsi": 7.0,
    "macd": 7.0,
    "adx": 5.0,
    "bb": 8.0,
    "vwap": 6.0,
    "volume": 5.0,
    "vol_profile": 6.0,
    "momentum": 6.0,
    "trend": 7.0,
    "mean_reversion": 9.0,
    "structure_stop": 4.0,
}

DEFAULT_CONFIG = {
    "threshold": 90.0,
    "calibration": 0.57,
    "conf_gap": 8.0,
    "stop_mult": 0.9,
    "tp_r": 2.2,
}


def load_weights() -> dict[str, float]:
    if WEIGHTS_PATH.exists():
        with open(WEIGHTS_PATH) as f:
            saved = json.load(f)
        return {k: float(saved.get(k, v)) for k, v in DEFAULT_FEATURE_WEIGHTS.items()}
    return dict(DEFAULT_FEATURE_WEIGHTS)


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    return cfg


def save_model(weights: dict[str, float], config: dict):
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WEIGHTS_PATH, "w") as f:
        json.dump({k: round(float(weights[k]), 4) for k in DEFAULT_FEATURE_WEIGHTS}, f, indent=2)
    with open(CONFIG_PATH, "w") as f:
        json.dump({k: config.get(k, DEFAULT_CONFIG[k]) for k in DEFAULT_CONFIG}, f, indent=2)


class FeatureEngine:

    @staticmethod
    def prepare(df: pd.DataFrame) -> pd.DataFrame:
        df = SignalIndicators.calculate(df)
        return ExtendedIndicators.calculate(df)

    @staticmethod
    def build_contributions(df: pd.DataFrame) -> dict[str, np.ndarray]:
        """Precompute per-rule buy/sell point contributions (values 0–1)."""
        n = len(df)
        price = df["close"].values
        e20 = df["ema20"].values
        e50 = df["ema50"].values
        e200 = df["ema200"].values
        rsi = df["rsi"].values
        macd = df["macd_diff"].values
        macd_prev = df["macd_diff_prev"].values
        adx = df["adx"].values
        bb_u = df["bb_upper"].values
        bb_m = df["bb_mid"].values
        bb_l = df["bb_lower"].values
        vwap = df["vwap"].values if "vwap" in df.columns else price
        poc = df["poc"].values if "poc" in df.columns else price
        vr = df["volume_ratio"].values if "volume_ratio" in df.columns else np.ones(n)
        mom = df["momentum_score"].values if "momentum_score" in df.columns else np.zeros(n)
        ema_slope = df["ema20_slope"].values if "ema20_slope" in df.columns else np.zeros(n)

        width = np.where(bb_u - bb_l > 0, bb_u - bb_l, np.nan)
        bb_pos = np.clip(np.where(np.isnan(width), 0.5, (price - bb_l) / width), 0, 1)

        bull_stack = (price > e20) & (e20 > e50) & (e50 > e200)
        bear_stack = (price < e20) & (e20 < e50) & (e50 < e200)
        vwap_dist = np.where(vwap > 0, (price - vwap) / vwap * 100, 0)
        ranging = adx <= 26
        strong = adx >= 28

        contribs: dict[str, tuple[np.ndarray, np.ndarray]] = {}

        contribs["ema"] = (
            bull_stack.astype(float) + ((price > e50) & (e20 > e50) & ~bull_stack).astype(float) * 0.6,
            bear_stack.astype(float) + ((price < e50) & (e20 < e50) & ~bear_stack).astype(float) * 0.6,
        )
        contribs["rsi"] = (
            (rsi < 35).astype(float) + ((rsi >= 45) & (rsi <= 58) & (price > e50)).astype(float) * 0.7,
            (rsi > 65).astype(float) + ((rsi >= 42) & (rsi <= 55) & (price < e50)).astype(float) * 0.7,
        )
        contribs["macd"] = (
            ((macd > 0) & (macd > macd_prev)).astype(float),
            ((macd < 0) & (macd < macd_prev)).astype(float),
        )
        contribs["adx"] = (
            (strong & (price > e50)).astype(float),
            (strong & (price < e50)).astype(float),
        )
        contribs["bb"] = (
            (bb_pos <= 0.15).astype(float) + ((price > bb_m) & (bb_pos <= 0.6)).astype(float) * 0.5,
            (bb_pos >= 0.85).astype(float) + ((price < bb_m) & (bb_pos >= 0.4)).astype(float) * 0.5,
        )
        contribs["vwap"] = (
            (vwap_dist > 0.15).astype(float),
            (vwap_dist < -0.15).astype(float),
        )
        contribs["vol_profile"] = (
            (price > poc).astype(float) * 0.5,
            (price < poc).astype(float) * 0.5,
        )
        contribs["volume"] = (
            (vr >= 1.3).astype(float) * 0.5,
            (vr >= 1.3).astype(float) * 0.5,
        )
        contribs["momentum"] = (
            (mom > 1.0).astype(float),
            (mom < -1.0).astype(float),
        )
        contribs["trend"] = (
            (ema_slope > 0.08).astype(float),
            (ema_slope < -0.08).astype(float),
        )
        contribs["mean_reversion"] = (
            (ranging & (rsi < 38) & (bb_pos <= 0.12)).astype(float),
            (ranging & (rsi > 62) & (bb_pos >= 0.88)).astype(float),
        )
        contribs["structure_stop"] = (np.zeros(n), np.zeros(n))  # used for stops only

        swing_sl = df["low"].rolling(20, min_periods=5).min().values
        swing_sh = df["high"].rolling(20, min_periods=5).max().values

        return {
            "contributions": contribs,
            "bear_stack": bear_stack.astype(float),
            "bull_stack": bull_stack.astype(float),
            "swing_sl": swing_sl,
            "swing_sh": swing_sh,
        }

    @staticmethod
    def apply_weights(
        cache: dict,
        weights: dict[str, float],
        calibration: float = 0.57,
    ) -> dict[str, np.ndarray]:
        contribs = cache["contributions"]
        n = len(cache["bear_stack"])
        buy_pts = np.zeros(n)
        sell_pts = np.zeros(n)
        max_pts = sum(weights.get(k, 1) for k in DEFAULT_FEATURE_WEIGHTS)

        for key in DEFAULT_FEATURE_WEIGHTS:
            w = weights.get(key, DEFAULT_FEATURE_WEIGHTS[key])
            b, s = contribs[key]
            buy_pts += b * w
            sell_pts += s * w

        # Counter-trend penalty
        buy_pts *= np.where(cache["bear_stack"], 0.7, 1.0)
        sell_pts *= np.where(cache["bull_stack"], 0.7, 1.0)

        cal = max(calibration, 0.01)
        raw_buy = np.clip(buy_pts / max(max_pts, 1), 0, 1)
        raw_sell = np.clip(sell_pts / max(max_pts, 1), 0, 1)
        buy_conf = np.clip(raw_buy / cal * 90, 0, 100)
        sell_conf = np.clip(raw_sell / cal * 90, 0, 100)

        return {
            "buy_confidence": buy_conf,
            "sell_confidence": sell_conf,
            "swing_sl": cache["swing_sl"],
            "swing_sh": cache["swing_sh"],
        }

    @staticmethod
    def _vector_scores(df: pd.DataFrame, weights: dict[str, float] | None = None) -> tuple[pd.Series, pd.Series]:
        w = weights or load_weights()
        cfg = load_config()
        cache = FeatureEngine.build_contributions(df)
        scored = FeatureEngine.apply_weights(cache, w, cfg.get("calibration", 0.57))
        return (
            pd.Series(scored["buy_confidence"], index=df.index),
            pd.Series(scored["sell_confidence"], index=df.index),
        )

    @staticmethod
    def precompute(df: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.DataFrame:
        w = weights or load_weights()
        buy_conf, sell_conf = FeatureEngine._vector_scores(df, w)
        out = df.copy()
        out["buy_confidence"] = buy_conf
        out["sell_confidence"] = sell_conf
        out["swing_sl"] = df["low"].rolling(20, min_periods=5).min()
        out["swing_sh"] = df["high"].rolling(20, min_periods=5).max()
        return out

    @staticmethod
    def signal_at(df: pd.DataFrame, i: int, threshold: float | None = None) -> dict:
        cfg = load_config()
        thresh = threshold if threshold is not None else cfg.get("threshold", 90)
        conf_gap = cfg.get("conf_gap", 8)
        row = df.iloc[i]
        buy_conf = float(row.get("buy_confidence", 0))
        sell_conf = float(row.get("sell_confidence", 0))

        if buy_conf >= thresh and buy_conf > sell_conf + conf_gap:
            direction, confidence = "BUY", buy_conf
        elif sell_conf >= thresh and sell_conf > buy_conf + conf_gap:
            direction, confidence = "SELL", sell_conf
        else:
            return {
                "signal": "WAIT", "confidence": 0, "confluence": 0,
                "setup_type": "none", "tp_price": None,
                "swing_lows": [], "swing_highs": [],
                "reasons": [f"Confidence below {thresh}"],
            }

        sl, sh = row.get("swing_sl"), row.get("swing_sh")
        swing_lows = [{"price": float(sl)}] if pd.notna(sl) else []
        swing_highs = [{"price": float(sh)}] if pd.notna(sh) else []

        return {
            "signal": direction,
            "confidence": round(confidence, 1),
            "confluence": int(round(confidence)),
            "setup_type": "ai_signal",
            "tp_price": None,
            "swing_lows": swing_lows,
            "swing_highs": swing_highs,
            "reasons": [f"AI confidence {confidence:.1f}/100 (threshold {thresh})"],
        }
