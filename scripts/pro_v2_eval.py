"""PRO V2 evaluation and comparison vs V1."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.market_context import MarketContextBuilder
from app.analysis.pro.engine import SignalEnginePro
from app.analysis.pro_v2.engine import SignalEngineProV2
from app.backtest.pro_backtester import run_pro_v2_backtest, save_report
from app.collectors.candles import CandleCollector
from app.config import DEFAULT_INTERVAL, DEFAULT_SYMBOL


def main() -> int:
    cache = Path(".cache/backtest_candles.csv")
    if cache.exists():
        import pandas as pd
        df = pd.read_csv(cache, parse_dates=["timestamp"])
    else:
        df = CandleCollector().get_candles(symbol=DEFAULT_SYMBOL, interval=DEFAULT_INTERVAL, limit=500)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache, index=False)

    v2_report = run_pro_v2_backtest(df, symbol=DEFAULT_SYMBOL, interval=DEFAULT_INTERVAL)
    save_report(v2_report, ".cache/pro_v2/backtest_report.json")

    ctx = MarketContextBuilder.build(df, symbol=DEFAULT_SYMBOL, interval=DEFAULT_INTERVAL)
    v1_last = SignalEnginePro.generate(ctx.df, context=ctx, indicators_calculated=True)
    v2_last = SignalEngineProV2.generate(ctx.df, context=ctx, indicators_calculated=True)

    comparison = {
        "v1_last_signal": v1_last["signal"],
        "v1_last_confidence": v1_last.get("confidence", 0),
        "v2_last_signal": v2_last["signal"],
        "v2_last_confidence": v2_last.get("confidence", 0),
        "v2_last_grade": v2_last.get("grade", "C"),
        "v2_backtest": {k: v for k, v in v2_report.items() if k != "trade_list"},
    }
    out = Path(".cache/pro_v2/comparison_report.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(comparison, f, indent=2)

    print(json.dumps(comparison, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
