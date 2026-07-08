from app.indicators.trend import TrendAnalyzer
from app.indicators.signals import SignalIndicators

from app.analysis.structure import StructureAnalyzer
from app.analysis.bos import BOSAnalyzer
from app.analysis.liquidity import LiquidityAnalyzer
from app.analysis.order_block import OrderBlockAnalyzer
from app.analysis.fvg import FVGAnalyzer


class SignalGenerator:

    @staticmethod
    def generate(df):

        df = SignalIndicators.calculate(df)

        trend = TrendAnalyzer.detect_trend(df)
        structure = StructureAnalyzer.analyze(df)
        bos = BOSAnalyzer.analyze(df)
        liquidity = LiquidityAnalyzer.analyze(df)
        orderblock = OrderBlockAnalyzer.analyze(df)
        fvg = FVGAnalyzer.analyze(df)

        last = df.iloc[-1]

        score = 0
        reasons = []

        # ================= EMA =================

        if last["ema20"] > last["ema50"] > last["ema200"]:
            score += 25
            reasons.append("EMA Bullish")

        elif last["ema20"] < last["ema50"] < last["ema200"]:
            score -= 25
            reasons.append("EMA Bearish")

        # ================= RSI =================

        if last["rsi"] > 60:
            score += 15
            reasons.append("RSI Strong")

        elif last["rsi"] < 40:
            score -= 15
            reasons.append("RSI Weak")

        # ================= MACD =================

        if last["macd"] > last["macd_signal"]:
            score += 20
            reasons.append("MACD Bullish")
        else:
            score -= 20
            reasons.append("MACD Bearish")

        # ================= TREND =================

        if trend == "BULLISH":
            score += 20
            reasons.append("Trend Bullish")

        elif trend == "BEARISH":
            score -= 20
            reasons.append("Trend Bearish")

        # ================= STRUCTURE =================

        if structure == "UPTREND":
            score += 15
            reasons.append("Market Structure Bullish")

        elif structure == "DOWNTREND":
            score -= 15
            reasons.append("Market Structure Bearish")

        # ================= BOS =================

        if bos == "BULLISH_BOS":
            score += 20
            reasons.append("Bullish BOS")

        elif bos == "BEARISH_BOS":
            score -= 20
            reasons.append("Bearish BOS")

        # ================= LIQUIDITY =================

        if liquidity:
            score += 5
            reasons.append("Liquidity Zone")

        # ================= ORDER BLOCK =================

        if orderblock:

            if orderblock["bullish"]:
                score += 10
                reasons.append("Bullish Order Block")

            if orderblock["bearish"]:
                score -= 10
                reasons.append("Bearish Order Block")

        # ================= FVG =================

        if fvg:

            if fvg["type"] == "BULLISH":
                score += 10
                reasons.append("Bullish FVG")

            elif fvg["type"] == "BEARISH":
                score -= 10
                reasons.append("Bearish FVG")

        # ================= SIGNAL =================

        if score >= 60:
            signal = "BUY"

        elif score <= -60:
            signal = "SELL"

        else:
            signal = "WAIT"

        return {
            "signal": signal,
            "score": score,
            "trend": trend,
            "structure": structure,
            "bos": bos,
            "liquidity": liquidity,
            "orderblock": orderblock,
            "fvg": fvg,
            "reasons": reasons
        }


if __name__ == "__main__":

    from app.collectors.candles import CandleCollector

    collector = CandleCollector()

    df = collector.get_candles()

    result = SignalGenerator.generate(df)

    print(result)