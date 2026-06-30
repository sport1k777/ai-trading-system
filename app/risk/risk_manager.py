class RiskManager:

    @staticmethod
    def calculate(price, atr, signal):

        if signal == "LONG":

            entry = price
            stop = price - atr

            tp1 = price + atr
            tp2 = price + atr * 2
            tp3 = price + atr * 3

        elif signal == "SHORT":

            entry = price
            stop = price + atr

            tp1 = price - atr
            tp2 = price - atr * 2
            tp3 = price - atr * 3

        else:

            return None

        rr = round(abs(tp3 - entry) / abs(entry - stop), 2)

        return {
            "entry": round(entry, 2),
            "stop": round(stop, 2),
            "tp1": round(tp1, 2),
            "tp2": round(tp2, 2),
            "tp3": round(tp3, 2),
            "rr": rr
        }