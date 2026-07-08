from app.config import MAX_STOP_ATR_MULT, STOP_ATR_MULT, TP_R_MULT


class RiskManager:

    SETUP_PARAMS = {
        "mean_reversion": {"stop_mult": 0.75, "tp_r": None},  # tp via bb_mid
        "momentum": {"stop_mult": 1.2, "tp_r": 2.5},
        "pullback": {"stop_mult": 1.0, "tp_r": 2.0},
    }

    @staticmethod
    def calculate(price, atr, signal, swing_low=None, swing_high=None, tp_price=None, setup_type="trend"):
        if signal not in ("BUY", "SELL") or atr is None or atr <= 0:
            return None

        params = RiskManager.SETUP_PARAMS.get(setup_type, {"stop_mult": STOP_ATR_MULT, "tp_r": TP_R_MULT})
        stop_mult = params["stop_mult"]
        tp_r = params.get("tp_r", TP_R_MULT)

        if signal == "BUY":
            atr_stop = price - stop_mult * atr
            structure_stop = (swing_low - 0.2 * atr) if swing_low else atr_stop
            stop = min(atr_stop, structure_stop)
            stop = max(stop, price - MAX_STOP_ATR_MULT * atr)
        else:
            atr_stop = price + stop_mult * atr
            structure_stop = (swing_high + 0.2 * atr) if swing_high else atr_stop
            stop = max(atr_stop, structure_stop)
            stop = min(stop, price + MAX_STOP_ATR_MULT * atr)

        entry = price
        risk = abs(entry - stop)
        if risk == 0:
            return None

        if tp_price is not None:
            tp1 = tp_price
        elif signal == "BUY":
            tp1 = entry + tp_r * risk
        else:
            tp1 = entry - tp_r * risk

        rr = round(abs(tp1 - entry) / risk, 2)

        return {
            "entry": round(entry, 2),
            "stop": round(stop, 2),
            "tp1": round(tp1, 2),
            "tp2": round(tp1, 2),
            "tp3": round(tp1, 2),
            "risk": round(risk, 4),
            "rr": rr,
        }

    @staticmethod
    def simulate_trade(
        signal: str,
        entry: float,
        atr: float,
        future_bars,
        swing_low=None,
        swing_high=None,
        tp_price=None,
        setup_type: str = "trend",
    ) -> dict:
        levels = RiskManager.calculate(
            entry, atr, signal, swing_low, swing_high,
            tp_price=tp_price, setup_type=setup_type,
        )
        if not levels:
            return {"result": "SKIP", "pnl_r": 0.0, "exit_price": entry}

        stop = levels["stop"]
        tp1 = levels["tp1"]
        risk = levels["risk"]

        for _, bar in future_bars.iterrows():
            high, low = float(bar["high"]), float(bar["low"])

            if signal == "BUY":
                if low <= stop:
                    return {"result": "LOSS", "pnl_r": -1.0, "exit_price": stop}
                if high >= tp1:
                    pnl_r = (tp1 - entry) / risk
                    return {"result": "WIN", "pnl_r": round(pnl_r, 3), "exit_price": tp1}
            else:
                if high >= stop:
                    return {"result": "LOSS", "pnl_r": -1.0, "exit_price": stop}
                if low <= tp1:
                    pnl_r = (entry - tp1) / risk
                    return {"result": "WIN", "pnl_r": round(pnl_r, 3), "exit_price": tp1}

        last_close = float(future_bars.iloc[-1]["close"])
        pnl_r = ((last_close - entry) if signal == "BUY" else (entry - last_close)) / risk
        return {"result": "TIMEOUT", "pnl_r": round(pnl_r, 3), "exit_price": round(last_close, 2)}
