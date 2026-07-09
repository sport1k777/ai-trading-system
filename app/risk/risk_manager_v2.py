"""Risk Manager V2 — PRO V2 setups with liquidity-based targets."""

from __future__ import annotations

from app.analysis.market_context import MarketContext
from app.config import MAX_STOP_ATR_MULT, PRO_V2_MIN_RR, STOP_ATR_MULT, TP_R_MULT
from app.risk.risk_manager import RiskManager
from app.risk.tp_mapper import map_take_profits


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

        price = ctx.price
        atr = ctx.atr
        levels = RiskManager.calculate(
            price,
            atr,
            direction,
            swing_low=swing_low,
            swing_high=swing_high,
            setup_type="pro_v2_signal",
        )
        if not levels:
            return None

        if levels["rr"] < PRO_V2_MIN_RR:
            return None

        risk_dist = abs(price - levels["stop"])
        if risk_dist > MAX_STOP_ATR_MULT * atr:
            return None

        tp1, tp2, tp3 = map_take_profits(
            ctx, direction, levels["entry"], levels["stop"], levels["tp1"],
        )
        rr = round(abs(tp1 - levels["entry"]) / risk_dist, 2) if risk_dist else 0

        return {
            "entry": levels["entry"],
            "stop": levels["stop"],
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
            "tp": tp1,
            "risk": levels["risk"],
            "rr": rr,
        }


# Register setup params on base RiskManager for compatibility
RiskManager.SETUP_PARAMS["pro_v2_signal"] = RiskManagerV2.SETUP_PARAMS["pro_v2_signal"]
