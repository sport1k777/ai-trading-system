"""
Self-learning scoring engine — genetic optimization of feature weights
via historical backtests. Trains until convergence or target metrics met.
"""

from __future__ import annotations

import copy
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from app.analysis.feature_engine import (
    CONFIG_PATH,
    DEFAULT_FEATURE_WEIGHTS,
    FeatureEngine,
    WEIGHTS_PATH,
    save_model,
)
from app.config import BACKTEST_MAX_HOLD_BARS, BACKTEST_WARMUP_BARS, MIN_BARS_BETWEEN_TRADES
from app.risk.risk_manager import RiskManager

CACHE_DIR = Path(".cache/longterm")
TRAINING_LOG = Path(".cache/training_log.json")
BEST_MODEL_PATH = Path(".cache/best_model.json")

SEGMENTS = [
    ("BTCUSDT", "15m"),
    ("BTCUSDT", "1h"),
    ("ETHUSDT", "15m"),
    ("ETHUSDT", "1h"),
    ("XRPUSDT", "1h"),
]

TARGETS = {
    "profit_factor": 1.7,
    "win_rate": 55.0,
    "max_drawdown_r": 15.0,
}

WEIGHT_KEYS = list(DEFAULT_FEATURE_WEIGHTS.keys())
GENE_KEYS = WEIGHT_KEYS + ["threshold", "calibration", "conf_gap", "stop_mult", "tp_r"]


@dataclass
class TrainingConfig:
    population_size: int = 80
    elite_size: int = 10
    mutation_rate: float = 0.28
    crossover_rate: float = 0.72
    patience: int = 30
    min_generations: int = 25
    max_generations: int = 200
    min_trades: int = 30


@dataclass
class Individual:
    genes: dict[str, float]
    fitness: float = -1e9
    metrics: dict = field(default_factory=dict)


def _random_genes() -> dict[str, float]:
    return {
        "ema": random.uniform(2, 14),
        "rsi": random.uniform(2, 12),
        "macd": random.uniform(2, 12),
        "adx": random.uniform(1, 10),
        "bb": random.uniform(2, 14),
        "vwap": random.uniform(1, 10),
        "volume": random.uniform(1, 8),
        "vol_profile": random.uniform(1, 10),
        "momentum": random.uniform(0.5, 8),
        "trend": random.uniform(2, 12),
        "mean_reversion": random.uniform(3, 16),
        "structure_stop": random.uniform(1, 8),
        "threshold": random.uniform(88, 98),
        "calibration": random.uniform(0.45, 0.70),
        "conf_gap": random.uniform(5, 18),
        "stop_mult": random.uniform(0.6, 1.1),
        "tp_r": random.uniform(1.5, 3.5),
    }


def _mutate_genes(genes: dict[str, float], rate: float = 0.25) -> dict[str, float]:
    out = copy.deepcopy(genes)
    for key in out:
        if random.random() < rate:
            if key == "threshold":
                out[key] = np.clip(out[key] + random.gauss(0, 1.5), 85, 99)
            elif key == "calibration":
                out[key] = np.clip(out[key] + random.gauss(0, 0.04), 0.40, 0.75)
            elif key == "conf_gap":
                out[key] = np.clip(out[key] + random.gauss(0, 2), 3, 25)
            elif key == "stop_mult":
                out[key] = np.clip(out[key] + random.gauss(0, 0.08), 0.5, 1.3)
            elif key == "tp_r":
                out[key] = np.clip(out[key] + random.gauss(0, 0.2), 1.2, 4.0)
            else:
                out[key] = np.clip(out[key] * random.uniform(0.7, 1.4), 0.5, 20)
    return out


def _crossover(a: dict, b: dict) -> dict:
    child = {}
    for key in a:
        child[key] = a[key] if random.random() < 0.5 else b[key]
        if random.random() < 0.15:
            child[key] = (a[key] + b[key]) / 2
    return child


def compute_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0, "profit_factor": 0,
            "net_profit_r": 0, "max_drawdown_r": 999, "sharpe_ratio": 0,
            "expectancy_r": 0,
        }

    r = np.array([t["pnl_r"] for t in trades])
    wins = sum(1 for t in trades if t["result"] == "WIN")
    gp = r[r > 0].sum()
    gl = abs(r[r < 0].sum())
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    max_dd = float((peak - equity).max())
    std_r = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    exp = float(r.mean())
    sharpe = (exp / std_r * np.sqrt(len(trades) / 1.14)) if std_r > 0 else 0.0

    return {
        "total_trades": len(trades),
        "wins": wins,
        "win_rate": round(wins / len(trades) * 100, 2),
        "profit_factor": round(gp / gl, 2) if gl > 0 else float("inf"),
        "net_profit_r": round(float(r.sum()), 2),
        "max_drawdown_r": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "expectancy_r": round(exp, 3),
    }


def targets_met(metrics: dict) -> bool:
    if metrics["total_trades"] < 30:
        return False
    return (
        metrics["profit_factor"] >= TARGETS["profit_factor"]
        and metrics["win_rate"] >= TARGETS["win_rate"]
        and metrics["max_drawdown_r"] <= TARGETS["max_drawdown_r"]
    )


def fitness(metrics: dict) -> float:
    if metrics["total_trades"] < 20:
        return -1e9

    pf = metrics["profit_factor"]
    wr = metrics["win_rate"]
    dd = metrics["max_drawdown_r"]
    net = metrics["net_profit_r"]
    sharpe = metrics["sharpe_ratio"]
    trades = metrics["total_trades"]

    score = (
        pf * 60
        + wr * 4
        + net * 1.5
        + sharpe * 15
        - max(0, dd - TARGETS["max_drawdown_r"]) * 12
        - max(0, TARGETS["profit_factor"] - pf) * 50
        - max(0, TARGETS["win_rate"] - wr) * 8
    )

    # Penalize overtrading (hurts WR and DD)
    if trades > 400:
        score -= (trades - 400) * 0.8
    elif trades < 80:
        score -= (80 - trades) * 0.3

    if targets_met(metrics):
        score += 5000

    return score


def _quality_seed() -> dict[str, float]:
    """High-selectivity seed biased toward mean-reversion and strict threshold."""
    return {
        "ema": random.uniform(4, 10),
        "rsi": random.uniform(5, 12),
        "macd": random.uniform(2, 8),
        "adx": random.uniform(2, 6),
        "bb": random.uniform(6, 14),
        "vwap": random.uniform(3, 8),
        "volume": random.uniform(2, 6),
        "vol_profile": random.uniform(3, 8),
        "momentum": random.uniform(0.5, 4),
        "trend": random.uniform(3, 8),
        "mean_reversion": random.uniform(10, 18),
        "structure_stop": random.uniform(2, 6),
        "threshold": random.uniform(93, 98),
        "calibration": random.uniform(0.48, 0.58),
        "conf_gap": random.uniform(10, 20),
        "stop_mult": random.uniform(0.55, 0.85),
        "tp_r": random.uniform(1.8, 2.8),
    }


class BacktestCache:
    """Pre-loaded segments with contribution matrices for fast evaluation."""

    def __init__(self):
        self.segments: list[dict] = []

    def load(self):
        for symbol, interval in SEGMENTS:
            path = CACHE_DIR / f"{symbol}_{interval}.csv"
            if not path.exists():
                continue
            df = pd.read_csv(path, parse_dates=["timestamp"])
            prepared = FeatureEngine.prepare(df)
            contrib = FeatureEngine.build_contributions(prepared)
            self.segments.append({
                "symbol": symbol,
                "interval": interval,
                "prepared": prepared,
                "contributions": contrib,
            })

    def evaluate(self, genes: dict[str, float]) -> list[dict]:
        weights = {k: genes[k] for k in WEIGHT_KEYS}
        threshold = genes["threshold"]
        calibration = genes["calibration"]
        conf_gap = genes["conf_gap"]
        stop_mult = genes["stop_mult"]
        tp_r = genes["tp_r"]

        all_trades: list[dict] = []
        for seg in self.segments:
            scored = FeatureEngine.apply_weights(
                seg["contributions"], weights, calibration,
            )
            trades = _simulate_segment(
                seg["prepared"], scored, threshold, conf_gap, stop_mult, tp_r,
            )
            all_trades.extend(trades)
        return all_trades


def _simulate_segment(
    df: pd.DataFrame,
    scored: dict[str, np.ndarray],
    threshold: float,
    conf_gap: float,
    stop_mult: float,
    tp_r: float,
) -> list[dict]:
    buy_conf = scored["buy_confidence"]
    sell_conf = scored["sell_confidence"]
    swing_sl = scored["swing_sl"]
    swing_sh = scored["swing_sh"]
    opens = df["open"].values
    atrs = df["atr"].values
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
            entry = opens[entry_idx]
            atr = atrs[i]
            if atr <= 0:
                continue

            sl = float(swing_sl[i]) if not np.isnan(swing_sl[i]) else None
            sh = float(swing_sh[i]) if not np.isnan(swing_sh[i]) else None

            future = df.iloc[entry_idx + 1 : entry_idx + 1 + BACKTEST_MAX_HOLD_BARS]
            if future.empty:
                continue

            outcome = RiskManager.simulate_trade(
                direction, float(entry), float(atr), future,
                swing_low=sl if direction == "BUY" else None,
                swing_high=sh if direction == "SELL" else None,
                setup_type="ai_signal",
            )
            trades.append({"result": outcome["result"], "pnl_r": outcome["pnl_r"]})
            last_trade = i
    finally:
        if orig:
            RiskManager.SETUP_PARAMS["ai_signal"] = orig

    return trades


class SelfLearningEngine:
    """Genetic optimizer that trains until convergence."""

    def __init__(self, config: TrainingConfig | None = None):
        self.config = config or TrainingConfig()
        self.cache = BacktestCache()
        self.best: Individual | None = None
        self.history: list[dict] = []
        self.total_evaluations = 0

    def _evaluate(self, genes: dict[str, float]) -> Individual:
        trades = self.cache.evaluate(genes)
        metrics = compute_metrics(trades)
        ind = Individual(genes=genes, fitness=fitness(metrics), metrics=metrics)
        self.total_evaluations += 1
        return ind

    def _seed_population(self) -> list[Individual]:
        pop: list[Individual] = []

        # Seed with current saved model if exists
        if BEST_MODEL_PATH.exists():
            try:
                with open(BEST_MODEL_PATH) as f:
                    saved = json.load(f)
                genes = saved.get("genes", {})
                if genes:
                    pop.append(self._evaluate(genes))
            except (json.JSONDecodeError, KeyError):
                pass

        if WEIGHTS_PATH.exists() and CONFIG_PATH.exists():
            with open(WEIGHTS_PATH) as f:
                w = json.load(f)
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            genes = {k: w.get(k, DEFAULT_FEATURE_WEIGHTS[k]) for k in WEIGHT_KEYS}
            genes.update({
                "threshold": cfg.get("threshold", 90),
                "calibration": cfg.get("calibration", 0.57),
                "conf_gap": cfg.get("conf_gap", 8),
                "stop_mult": cfg.get("stop_mult", 0.9),
                "tp_r": cfg.get("tp_r", 2.2),
            })
            pop.append(self._evaluate(genes))

        while len(pop) < self.config.population_size:
            if len(pop) < self.config.population_size // 2:
                pop.append(self._evaluate(_quality_seed()))
            else:
                pop.append(self._evaluate(_random_genes()))

        return pop

    def train(self) -> Individual:
        print("=" * 60)
        print("SELF-LEARNING SCORING ENGINE — TRAINING")
        print("=" * 60)
        print(f"Targets: PF>{TARGETS['profit_factor']} WR>{TARGETS['win_rate']}% DD<{TARGETS['max_drawdown_r']}R")
        print(f"Population: {self.config.population_size} | Patience: {self.config.patience} gen")

        t0 = time.time()
        self.cache.load()
        print(f"Loaded {len(self.cache.segments)} segments ({time.time()-t0:.1f}s)\n")

        population = self._seed_population()
        population.sort(key=lambda x: x.fitness, reverse=True)
        self.best = copy.deepcopy(population[0])

        best_fitness = self.best.fitness
        stale = 0
        generation = 0

        self._log_generation(generation, population[0])
        self._save_best(self.best, generation)

        while generation < self.config.max_generations:
            generation += 1
            new_pop: list[Individual] = []

            # Elitism
            elites = population[: self.config.elite_size]
            new_pop.extend(copy.deepcopy(elites))

            # Breed
            while len(new_pop) < self.config.population_size:
                if random.random() < self.config.crossover_rate:
                    p1, p2 = random.sample(population[:40], 2)
                    child_genes = _crossover(p1.genes, p2.genes)
                else:
                    child_genes = _mutate_genes(random.choice(population[:30]).genes, rate=0.4)

                child_genes = _mutate_genes(child_genes, rate=self.config.mutation_rate)
                new_pop.append(self._evaluate(child_genes))

            population = sorted(new_pop, key=lambda x: x.fitness, reverse=True)[: self.config.population_size]
            top = population[0]

            if top.fitness > best_fitness + 0.01:
                best_fitness = top.fitness
                self.best = copy.deepcopy(top)
                stale = 0
                self._save_best(top, generation)
            else:
                stale += 1

            if generation % 5 == 0 or stale == 0:
                self._log_generation(generation, top)

            if targets_met(top.metrics):
                print(f"\n*** ALL TARGETS MET at generation {generation} ***")
                self.best = copy.deepcopy(top)
                self._save_best(top, generation)
                break

            if generation >= self.config.min_generations and stale >= self.config.patience:
                print(f"\n*** CONVERGED at generation {generation} (no improvement for {stale} gen) ***")
                break

        self._finalize()
        return self.best

    def _log_generation(self, gen: int, ind: Individual):
        m = ind.metrics
        met = targets_met(m)
        print(
            f"Gen {gen:4d} | evals={self.total_evaluations:5d} | "
            f"fitness={ind.fitness:8.1f} | trades={m.get('total_trades', 0):4d} | "
            f"WR={m.get('win_rate', 0):5.1f}% PF={m.get('profit_factor', 0):4.2f} | "
            f"net={m.get('net_profit_r', 0):+7.1f}R DD={m.get('max_drawdown_r', 0):5.1f}R | "
            f"{'TARGETS MET' if met else 'training...'}"
        )
        self.history.append({
            "generation": gen,
            "fitness": ind.fitness,
            "metrics": m,
            "targets_met": met,
            "evaluations": self.total_evaluations,
        })

    def _save_best(self, ind: Individual, generation: int):
        weights = {k: round(ind.genes[k], 4) for k in WEIGHT_KEYS}
        config = {
            "threshold": round(ind.genes["threshold"], 2),
            "calibration": round(ind.genes["calibration"], 4),
            "conf_gap": round(ind.genes["conf_gap"], 2),
            "stop_mult": round(ind.genes["stop_mult"], 3),
            "tp_r": round(ind.genes["tp_r"], 2),
        }
        save_model(weights, config)
        payload = {
            "generation": generation,
            "fitness": float(ind.fitness),
            "metrics": ind.metrics,
            "genes": {k: round(float(v), 4) for k, v in ind.genes.items()},
            "targets_met": bool(targets_met(ind.metrics)),
            "evaluations": self.total_evaluations,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        BEST_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BEST_MODEL_PATH, "w") as f:
            json.dump(payload, f, indent=2)

    def _finalize(self):
        with open(TRAINING_LOG, "w") as f:
            json.dump(self.history, f, indent=2, default=str)

        m = self.best.metrics if self.best else {}
        print("\n" + "=" * 60)
        print("TRAINING COMPLETE")
        print("=" * 60)
        print(f"Total evaluations : {self.total_evaluations}")
        print(f"Best fitness      : {self.best.fitness:.1f}")
        print(f"Trades            : {m.get('total_trades', 0)}")
        print(f"Win Rate          : {m.get('win_rate', 0)}%  (target >{TARGETS['win_rate']}%)")
        print(f"Profit Factor     : {m.get('profit_factor', 0)}  (target >{TARGETS['profit_factor']})")
        print(f"Max Drawdown      : {m.get('max_drawdown_r', 0)}R  (target <{TARGETS['max_drawdown_r']}R)")
        print(f"Net Profit        : {m.get('net_profit_r', 0)}R")
        print(f"Sharpe            : {m.get('sharpe_ratio', 0)}")
        print(f"Targets met       : {targets_met(m)}")
        print(f"Best model saved  : {BEST_MODEL_PATH}")
