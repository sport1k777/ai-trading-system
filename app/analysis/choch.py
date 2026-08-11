from __future__ import annotations

import pandas as pd

from app.analysis.structure_persistence import analyze_choch_persistent


class CHOCHAnalyzer:
    """Change of character with configurable closed-bar persistence."""

    @staticmethod
    def analyze(df: pd.DataFrame, *, lookback: int | None = None) -> str:
        return analyze_choch_persistent(df, lookback=lookback)
