from app.collectors.candles import CandleCollector
from app.indicators.signals import SignalIndicators
from app.indicators.trend import TrendAnalyzer

from app.analysis.structure import StructureAnalyzer
from app.analysis.swing import SwingAnalyzer
from app.analysis.bos import BOSAnalyzer
from app.analysis.signal_generator import SignalGenerator

from app.risk.risk_manager import RiskManager


def main():

    print("\n==============================")
    print("      AI TRADING SYSTEM")
    print("==============================")

    # Завантажуємо свічки
    collector = CandleCollector()
    df = collector.get_candles()

    # Рахуємо індикатори
    df = SignalIndicators.calculate(df)

    # Тренд
    trend = TrendAnalyzer.detect_trend(df)

    # Структура
    structure = StructureAnalyzer.analyze(df)

    # BOS
    bos = BOSAnalyzer.analyze(df)

    # Swing High / Low
    highs, lows = SwingAnalyzer.analyze(df)

    # Генеруємо сигнал
    signal = SignalGenerator.generate(df)

    # Risk Manager
    price = df.iloc[-1]["close"]
    atr = df.iloc[-1]["atr"]

    risk = RiskManager.calculate(
        price,
        atr,
        signal["signal"]
    )

    print("\n========== RESULT ==========")

    print(f"Trend      : {trend}")
    print(f"Structure  : {structure}")
    print(f"BOS        : {bos}")

    print(f"Signal     : {signal['signal']}")
    print(f"Score      : {signal['score']}")

    print("\nReasons:")

    for reason in signal["reasons"]:
        print(f"- {reason}")

    print("\nLast Swing High:")
    print(highs[-1])

    print("\nLast Swing Low:")
    print(lows[-1])

    if risk:

        print("\n========== RISK ==========")

        print(f"Entry : {risk['entry']}")
        print(f"Stop  : {risk['stop']}")
        print(f"TP1   : {risk['tp1']}")
        print(f"TP2   : {risk['tp2']}")
        print(f"TP3   : {risk['tp3']}")
        print(f"RR    : 1:{risk['rr']}")

    print("\nSystem Ready ✅")


if __name__ == "__main__":
    main()