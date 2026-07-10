"""Signal Engine PRO package."""

__all__ = ["SignalEnginePro"]


def __getattr__(name: str):
    if name == "SignalEnginePro":
        from app.analysis.pro.engine import SignalEnginePro

        return SignalEnginePro
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
