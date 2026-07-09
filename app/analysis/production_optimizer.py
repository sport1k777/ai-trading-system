"""
Production-grade walk-forward optimizer for the AI Signal Engine.
Optimizes for cross-symbol stability — rejects configs that help one asset but hurt others.
"""

from __future__ import annotations

import copy
import itertools
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.analysis.feature_engine import (
    DEFAULT_CONFIG,
    DEFAULT_FEATURE_WEIGHTS,
    FeatureEngine,
    load_config,
    load_weights,
    save_model,
)
from app.config import BACKTEST_MAX_HOLD_BARS, BACKTEST_WARMUP_BARS, MIN_BARS_BETWEEN_TRADES
from app.risk.risk_manager import RiskManager

PRODUCTION_DIR = Path(".cache/production")
PRODUCTION_MODEL = PRODUCTION_DIR / "production_model.json"
PRODUCTION_REPORT = PRODUCTION_DIR / "production_report.json"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
INTERVALS = {"15m": "15", "1h": "60", "4h": "240"}

WEIGHT_KEYS = list(DEFAULT_FEATURE_WEIGHTS.keys())
GENE_KEYS = WEIGHT_KEYS + ["threshold", "calibration", "conf_gap", "stop_mult", "tp_r"]

TARGET_PF = 1.5
MIN_SEGMENT_PF = 0.95
MIN_SEGMENT_TRADES = 8
TRAIN_RATIO = 0.70


@dataclass
class SegmentData:
    symbol: str
    interval: str
    prepared: object  # pd.DataFrame
    cache: dict
    train_end: int


@dataclass
class ModelGenes:
    weights: dict[str, float]
    threshold: float
    calibration: float
    conf_gap: float
    stop_mult: float
    tp_r: float

    def to_dict(self) -> dict:
        return {
            **self.weights,
            "threshold": self.threshold,
            "calibration": self.calibration,
            "conf_gap": self.conf_gap,
            "stop_mult": self.stop_mult,
            "tp_r": self.tp_r,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ModelGenes:
        weights = {k: float(d[k]) for k in WEIGHT_KEYS}
        return cls(
            weights=weights,
            threshold=float(d.get("threshold", 92)),
            calibration=float(d.get("calibration", 0.57)),
            conf_gap=float(d.get("conf_gap", 8)),
            stop_mult=float(d.get("stop_mult", 0.85)),
            tp_r=float(d.get("tp_r", 2.0)),
        )


def compute_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0, "profit_factor": 0,
            "net_profit_r": 0, "max_drawdown_r": 0, "expectancy_r": 0, "avg_rr": 0,
        }
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
        "wins": len(wins),
        "win_rate": round(len(wins) / len(trades) * 100, 2),
        "profit_factor": round(gp / gl, 2) if gl > 0 else float("inf"),
        "net_profit_r": round(float(r.sum()), 2),
        "max_drawdown_r": round(max_dd, 2),
        "expectancy_r": round(float(r.mean()), 3),
        "avg_rr": round(avg_rr, 2),
    }


def _simulate_range(
    seg: SegmentData,
    scored: dict,
    genes: ModelGenes,
    bar_start: int,
    bar_end: int,
) -> list[dict]:
    df = seg.prepared
    buy_conf = scored["buy_confidence"]
    sell_conf = scored["sell_confidence"]
    opens = df["open"].values
    atrs = df["atr"].values
    swing_sl = scored["swing_sl"]
    swing_sh = scored["swing_sh"]

    trades: list[dict] = []
    last_trade = -MIN_BARS_BETWEEN_TRADES
    start = max(BACKTEST_WARMUP_BARS, bar_start)
    end = min(bar_end, len(df) - BACKTEST_MAX_HOLD_BARS - 1)

    orig = RiskManager.SETUP_PARAMS.get("ai_signal", {}).copy()
    RiskManager.SETUP_PARAMS["ai_signal"] = {
        "stop_mult": genes.stop_mult, "tp_r": genes.tp_r,
    }

    try:
        for i in range(start, end):
            if i - last_trade < MIN_BARS_BETWEEN_TRADES:
                continue
            bc, sc = buy_conf[i], sell_conf[i]
            if bc >= genes.threshold and bc > sc + genes.conf_gap:
                direction = "BUY"
            elif sc >= genes.threshold and sc > bc + genes.conf_gap:
                direction = "SELL"
            else:
                continue

            entry_idx = i + 1
            if entry_idx >= len(df):
                continue
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
                "symbol": seg.symbol,
                "interval": seg.interval,
                "result": outcome["result"],
                "pnl_r": outcome["pnl_r"],
                "signal": direction,
            })
            last_trade = i
    finally:
        if orig:
            RiskManager.SETUP_PARAMS["ai_signal"] = orig

    return trades


def evaluate_model(
    segments: list[SegmentData],
    genes: ModelGenes,
    *,
    mode: str = "full",
) -> tuple[list[dict], list[dict]]:
    """Returns (per_segment_metrics, all_trades). mode: full | train | oos."""
    per_seg: list[dict] = []
    all_trades: list[dict] = []

    for seg in segments:
        scored = FeatureEngine.apply_weights(seg.cache, genes.weights, genes.calibration)
        n = len(seg.prepared)
        if mode == "train":
            trades = _simulate_range(seg, scored, genes, BACKTEST_WARMUP_BARS, seg.train_end)
        elif mode == "oos":
            trades = _simulate_range(seg, scored, genes, seg.train_end, n)
        else:
            trades = _simulate_range(seg, scored, genes, BACKTEST_WARMUP_BARS, n)

        m = compute_metrics(trades)
        m["symbol"] = seg.symbol
        m["interval"] = seg.interval
        per_seg.append(m)
        all_trades.extend(trades)

    return per_seg, all_trades


def robust_fitness(per_seg: list[dict]) -> float:
    """Maximin-style fitness — rewards stable PF across all segments."""
    active = [m for m in per_seg if m["total_trades"] >= 5]
    if len(active) < 2:
        return -1e9

    pfs = [m["profit_factor"] for m in active]
    min_pf = min(pfs)
    avg_pf = float(np.mean(pfs))
    std_pf = float(np.std(pfs)) if len(pfs) > 1 else 0

    nets = [m["net_profit_r"] for m in active]
    avg_exp = float(np.mean([m["expectancy_r"] for m in active]))
    avg_dd = float(np.mean([m["max_drawdown_r"] for m in active]))
    total_trades = sum(m["total_trades"] for m in active)

    score = (
        min_pf * 100
        + avg_pf * 50
        - std_pf * 30
        + avg_exp * 80
        - avg_dd * 0.5
        + min(1.0, total_trades / 200) * 15
    )

    if min_pf < MIN_SEGMENT_PF:
        score -= (MIN_SEGMENT_PF - min_pf) * 150
    if min(nets) < 0:
        score -= abs(min(nets)) * 2
    if max(pfs) > min_pf * 2.5 and min_pf < 1.1:
        score -= 50

    if avg_pf >= TARGET_PF and min_pf >= 1.1:
        score += 100

    return score


@dataclass
class ProductionOptimizer:
    segments: list[SegmentData] = field(default_factory=list)
    best: ModelGenes | None = None
    best_fitness: float = -1e9
    history: list[dict] = field(default_factory=list)
    _baseline_oos: list[dict] = field(default_factory=list)

    def load_segments(self, cache_dir: Path):
        import pandas as pd
        self.segments = []
        for symbol in SYMBOLS:
            for interval in INTERVALS:
                path = cache_dir / f"{symbol}_{interval}.csv"
                if not path.exists():
                    continue
                df = pd.read_csv(path, parse_dates=["timestamp"])
                if len(df) < BACKTEST_WARMUP_BARS + BACKTEST_MAX_HOLD_BARS + 100:
                    continue
                prepared = FeatureEngine.prepare(df)
                cache = FeatureEngine.build_contributions(prepared)
                train_end = int(len(df) * TRAIN_RATIO)
                self.segments.append(SegmentData(
                    symbol=symbol, interval=interval,
                    prepared=prepared, cache=cache, train_end=train_end,
                ))

    def _evaluate_genes(self, genes: ModelGenes) -> dict:
        train_seg, _ = evaluate_model(self.segments, genes, mode="train")
        oos_seg, _ = evaluate_model(self.segments, genes, mode="oos")
        train_fit = robust_fitness(train_seg)
        oos_fit = robust_fitness(oos_seg)
        # Weight OOS heavily to prevent overfitting
        combined = oos_fit * 0.65 + train_fit * 0.35
        return {
            "fitness": combined,
            "train_fitness": train_fit,
            "oos_fitness": oos_fit,
            "train_segments": train_seg,
            "oos_segments": oos_seg,
        }

    def _base_genes(self) -> ModelGenes:
        try:
            w = load_weights()
            c = load_config()
            return ModelGenes.from_dict({**w, **c})
        except Exception:
            return ModelGenes(
                weights=copy.deepcopy(DEFAULT_FEATURE_WEIGHTS),
                threshold=92.0,
                calibration=0.57,
                conf_gap=8.0,
                stop_mult=0.85,
                tp_r=2.0,
            )

    def _mutate(self, genes: ModelGenes, scale: float = 0.15) -> ModelGenes:
        d = genes.to_dict()
        for k in WEIGHT_KEYS:
            if random.random() < 0.3:
                d[k] = np.clip(d[k] * random.uniform(1 - scale, 1 + scale), 2, 16)
        if random.random() < 0.4:
            d["threshold"] = np.clip(d["threshold"] + random.gauss(0, 0.8), 90, 96)
        if random.random() < 0.3:
            d["calibration"] = np.clip(d["calibration"] + random.gauss(0, 0.03), 0.52, 0.62)
        if random.random() < 0.3:
            d["conf_gap"] = np.clip(d["conf_gap"] + random.gauss(0, 1.5), 5, 12)
        if random.random() < 0.3:
            d["stop_mult"] = np.clip(d["stop_mult"] + random.gauss(0, 0.06), 0.65, 1.0)
        if random.random() < 0.3:
            d["tp_r"] = np.clip(d["tp_r"] + random.gauss(0, 0.15), 1.6, 2.8)
        return ModelGenes.from_dict(d)

    def _try(self, genes: ModelGenes) -> bool:
        result = self._evaluate_genes(genes)
        fit = result["fitness"]

        # Improvement-only: must not hurt any OOS segment vs baseline
        if self._baseline_oos and fit > self.best_fitness:
            oos = result["oos_segments"]
            for base in self._baseline_oos:
                match = next(
                    (m for m in oos if m["symbol"] == base["symbol"] and m["interval"] == base["interval"]),
                    None,
                )
                if match and base["total_trades"] >= 5 and match["total_trades"] >= 5:
                    if match["profit_factor"] < base["profit_factor"] * 0.92:
                        return False

        if fit > self.best_fitness:
            self.best_fitness = fit
            self.best = copy.deepcopy(genes)
            active = [m for m in result["oos_segments"] if m["total_trades"] >= 5]
            self.history.append({
                "fitness": fit,
                "genes": genes.to_dict(),
                "oos_pf_avg": round(float(np.mean([m["profit_factor"] for m in active])), 2) if active else 0,
                "oos_min_pf": round(min((m["profit_factor"] for m in active), default=0), 2),
            })
            return True
        return False

    def optimize(
        self,
        *,
        grid_phase: bool = True,
        genetic_generations: int = 60,
        patience: int = 20,
    ) -> ModelGenes:
        print(f"Loaded {len(self.segments)} segments for walk-forward optimization")

        saved = self._base_genes()
        baseline_result = self._evaluate_genes(saved)
        self._baseline_oos = baseline_result["oos_segments"]
        self.best = copy.deepcopy(saved)
        self.best_fitness = baseline_result["fitness"]
        print(f"  Baseline OOS fitness: {self.best_fitness:.1f}")

        candidates: list[ModelGenes] = [saved]
        base_w = copy.deepcopy(saved.weights)

        if grid_phase:
            for th, gap, sm, tp, cal in itertools.product(
                [90, 91, 92, 93],
                [6, 7, 8, 9],
                [0.82, 0.87, 0.92],
                [1.9, 2.0, 2.2],
                [0.50, 0.52, 0.55],
            ):
                candidates.append(ModelGenes(
                    weights=copy.deepcopy(base_w),
                    threshold=th, calibration=cal, conf_gap=gap,
                    stop_mult=sm, tp_r=tp,
                ))

        for mr, bb, mom in [(17, 12, 1.0), (19, 11, 1.5), (15, 13, 2)]:
            g = copy.deepcopy(saved)
            g.weights["mean_reversion"] = mr
            g.weights["bb"] = bb
            g.weights["momentum"] = mom
            candidates.append(g)

        print(f"[Phase 1] Evaluating {len(candidates)} configs (walk-forward)...")
        for g in candidates:
            self._try(g)

        print(f"  Best after grid: fitness={self.best_fitness:.1f}")

        print(f"\n[Phase 2] Genetic refinement ({genetic_generations} gen max)...")
        stale = 0
        for gen in range(genetic_generations):
            batch = [self.best]
            for _ in range(25):
                batch.append(self._mutate(self.best, scale=0.06 + random.random() * 0.08))
            improved_any = False
            for g in batch:
                if self._try(g):
                    improved_any = True
            stale = 0 if improved_any else stale + 1

            if gen % 10 == 0:
                self._log(gen)
            if stale >= patience:
                print(f"Converged at generation {gen}")
                break

        return self.best

    def _log(self, gen: int):
        if not self.best:
            return
        _, oos_trades = evaluate_model(self.segments, self.best, mode="oos")
        m = compute_metrics(oos_trades)
        print(f"  Gen {gen}: fitness={self.best_fitness:.1f} OOS PF={m.get('profit_factor', 0)} "
              f"trades={m.get('total_trades', 0)}")

    def save_production_model(self):
        if not self.best:
            return
        PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self.best.to_dict(),
            "fitness": self.best_fitness,
            "optimized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with open(PRODUCTION_MODEL, "w") as f:
            json.dump(payload, f, indent=2)
        save_model(self.best.weights, {
            "threshold": self.best.threshold,
            "calibration": self.best.calibration,
            "conf_gap": self.best.conf_gap,
            "stop_mult": self.best.stop_mult,
            "tp_r": self.best.tp_r,
        })


def production_readiness_score(
    per_seg: list[dict],
    oos_combined: dict,
    segments_loaded: int,
    segments_expected: int,
) -> tuple[int, list[str]]:
    """Score 0-100 with weakness notes."""
    score = 0
    weaknesses: list[str] = []

    active = [m for m in per_seg if m["total_trades"] >= MIN_SEGMENT_TRADES]
    pfs = [m["profit_factor"] for m in active]
    min_pf = min(pfs) if pfs else 0
    avg_pf = float(np.mean(pfs)) if pfs else 0

    # Coverage (15 points)
    cov = segments_loaded / max(segments_expected, 1)
    score += int(cov * 15)
    if cov < 0.8:
        weaknesses.append(f"Data coverage incomplete ({segments_loaded}/{segments_expected} segments)")

    # PF (30 points)
    if avg_pf >= 1.5:
        score += 30
    elif avg_pf >= 1.3:
        score += 20
        weaknesses.append(f"Average PF {avg_pf} below target 1.5")
    elif avg_pf >= 1.1:
        score += 10
        weaknesses.append(f"Average PF {avg_pf} marginal")
    else:
        weaknesses.append(f"Average PF {avg_pf} insufficient")

    # Min segment PF (20 points)
    if min_pf >= 1.2:
        score += 20
    elif min_pf >= 1.0:
        score += 12
        weaknesses.append(f"Weakest segment PF {min_pf} near breakeven")
    else:
        weaknesses.append(f"Weakest segment PF {min_pf} unprofitable")

    # Expectancy (15 points)
    if oos_combined.get("expectancy_r", 0) > 0.05:
        score += 15
    elif oos_combined.get("expectancy_r", 0) > 0:
        score += 8
        weaknesses.append("Expectancy positive but thin")
    else:
        weaknesses.append("Non-positive expectancy")

    # Drawdown (10 points)
    if oos_combined.get("max_drawdown_r", 999) <= 30:
        score += 10
    elif oos_combined.get("max_drawdown_r", 999) <= 50:
        score += 5
        weaknesses.append(f"Drawdown {oos_combined.get('max_drawdown_r')}R elevated")

    # Stability (10 points)
    if pfs and np.std(pfs) < 0.35:
        score += 10
    elif pfs and np.std(pfs) < 0.6:
        score += 5
        weaknesses.append("PF variance across segments is high")
    else:
        weaknesses.append("Unstable PF across symbols/timeframes")

    losing = [m for m in active if m["profit_factor"] < 1.0]
    for m in losing:
        weaknesses.append(f"{m['symbol']} {m['interval']}: PF {m['profit_factor']} losing")

    return min(100, score), weaknesses
