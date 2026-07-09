#!/usr/bin/env python3
"""Train the self-learning scoring engine until convergence."""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.self_learning_engine import SelfLearningEngine, TrainingConfig


def main():
    config = TrainingConfig()
    engine = SelfLearningEngine(config)
    best = engine.train()

    if best and best.metrics:
        print("\nOptimized weights saved to .cache/ai_weights.json")
        print("Run: PYTHONPATH=. python3 scripts/long_term_eval.py")


if __name__ == "__main__":
    main()
