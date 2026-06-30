from app.indicators.trend import TrendAnalyzer
from app.indicators.signals import SignalIndicators


class SignalGenerator:

    @staticmethod
    def generate(df):

        # Додаємо індикатори
        df = SignalIndicators.calculate(df)

        # Визначаємо тренд
        trend = TrendAnalyzer.detect_trend(df)

        last = df.iloc[-1]

        score = 0
        reasons = []

        # EMA
        if last["ema20"] > last["ema50"] > last["ema200"]:
            score += 30
            reasons.append("EMA Bullish")

        elif last["ema20"] < last["ema50"] < last["ema200"]:
            score -= 30
            reasons.append("EMA Bearish")

        # RSI
        if 50 < last["rsi"] < 70:
            score += 15
            reasons.append("RSI Strong")

        elif 30 < last["rsi"] < 50:
            score -= 15
            reasons.append("RSI Weak")

        # MACD
        if last["macd"] > last["macd_signal"]:
            score += 20
            reasons.append("MACD Bullish")
        else:
            score -= 20
            reasons.append("MACD Bearish")

        # Trend
        if trend == "BULLISH":
            score += 35
        elif trend == "BEARISH":
            score -= 35

        # Рішення
        if score >= 50:
            signal = "BUY"
        elif score <= -50:
            signal = "SELL"
        else:
            signal = "WAIT"

        return {
            "signal": signal,
            "score": score,
            "trend": trend,
            "reasons": reasons
        }


if __name__ == "__main__":

     from app.collectors.candles import CandleCollector

     collector = CandleCollector()

     df = collector.get_candles()

     result = SignalGenerator.generate(df)

     print("\n========== SIGNAL ==========")
     print(f"Signal : {result['signal']}")
     print(f"Score  : {result['score']}")
     print(f"Trend  : {result['trend']}")

     print("\nReasons:")
     for reason in result["reasons"]:
        print(f"- {reason}")