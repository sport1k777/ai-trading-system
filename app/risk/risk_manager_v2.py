"""Risk Manager V2 — PRO V2 setups with structural trade-plan engine."""

from __future__ import annotations

from app.analysis.market_context import MarketContext
from app.risk.risk_manager import RiskManager
from app.risk.trade_plan_engine import build_trade_plan


class RiskManagerV2:
    SETUP_PARAMS = {
        "pro_v2_signal": {"stop_mult": 0.9, "tp_r": 2.2},
    }

    @staticmethod
    def calculate(
        ctx: MarketContext,
        direction: str,
        *,
        swing_low=None,
        swing_high=None,
    ) -> dict | None:
        if direction not in ("BUY", "SELL"):
            return None

        sl = swing_low["price"] if isinstance(swing_low, dict) else swing_low
        sh = swing_high["price"] if isinstance(swing_high, dict) else swing_high
        return build_trade_plan(ctx, direction, swing_low=sl, swing_high=sh)


RiskManager.SETUP_PARAMS["pro_v2_signal"] = RiskManagerV2.SETUP_PARAMS["pro_v2_signal"]
