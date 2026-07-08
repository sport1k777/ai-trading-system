from app.collectors.candles import CandleCollector
from app.indicators.signals import SignalIndicators
from app.indicators.trend import TrendAnalyzer

from app.analysis.structure import StructureAnalyzer
from app.analysis.swing import SwingAnalyzer
from app.analysis.bos import BOSAnalyzer
from app.analysis.signal_generator import SignalGenerator
from app.analysis.liquidity import LiquidityAnalyzer
from app.analysis.order_block import OrderBlockAnalyzer
from app.analysis.fvg import FVGAnalyzer

from app.risk.risk_manager import RiskManager


def main():

    print("\n==============================")
    print("      AI TRADING SYSTEM")
    print("==============================")

    # Завантаження свічок
    collector = CandleCollector()
    df = collector.get_candles()

    # Індикатори
    df = SignalIndicators.calculate(df)

    # Аналіз
    trend = TrendAnalyzer.detect_trend(df)
    structure = StructureAnalyzer.analyze(df)
    bos = BOSAnalyzer.analyze(df)

    liquidity = LiquidityAnalyzer.analyze(df)
    order_block = OrderBlockAnalyzer.analyze(df)
    fvg = FVGAnalyzer.analyze(df)

    highs, lows = SwingAnalyzer.analyze(df)

    signal = SignalGenerator.generate(df)

    price = df.iloc[-1]["close"]
    atr = df.iloc[-1]["atr"]

    risk = RiskManager.calculate(
        price,
        atr,
        signal["signal"]
    )

    print("\n========== RESULT ==========\n")

    print(f"Trend       : {trend}")
    print(f"Structure   : {structure}")
    print(f"BOS         : {bos}")
    print(f"Liquidity   : {liquidity}")
    print(f"Order Block : {order_block}")
    print(f"FVG         : {fvg}")

    print()

    print(f"Signal      : {signal['signal']}")
    print(f"Score       : {signal['score']}")

    print("\nReasons:")

    for reason in signal["reasons"]:
        print(f"- {reason}")

    print("\nLast Swing High:")
    print(highs[-1])

    print("\nLast Swing Low:")
    print(lows[-1])

    if risk:

        print("\n========== RISK ==========\n")

        print(f"Entry : {risk['entry']}")
        print(f"Stop  : {risk['stop']}")
        print(f"TP1   : {risk['tp1']}")
        print(f"TP2   : {risk['tp2']}")
        print(f"TP3   : {risk['tp3']}")
        print(f"RR    : 1:{risk['rr']}")

    print("\nSystem Ready ✅")


if __name__ == "__main__":
    main()