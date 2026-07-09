"""
Signal generator — delegates to the AI Signal Engine.
Preserves the same interface for backtester, pipeline, and scanner compatibility.
"""

from app.analysis.ai_signal_engine import AISignalEngine


class SignalGenerator:
    """Backward-compatible wrapper around AISignalEngine."""

    REQUIRED = AISignalEngine.REQUIRED

    @staticmethod
    def generate(df, *, indicators_calculated: bool = False):
        return AISignalEngine.generate(df, indicators_calculated=indicators_calculated)
