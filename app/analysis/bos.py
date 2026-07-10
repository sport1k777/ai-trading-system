from __future__ import annotations

import pandas as pd

from app.analysis.structure_persistence import analyze_bos_persistent


class BOSAnalyzer:
    """Break of structure with configurable closed-bar persistence."""

    @staticmethod
    def analyze(df: pd.DataFrame, *, lookback: int | None = None) -> str:
        return analyze_bos_persistent(df, lookback=lookback)
