from app.collectors.candles import CandleCollector
from app.indicators.signals import SignalIndicators
from app.analysis.signal_generator import SignalGenerator
from app.risk.risk_manager import RiskManager

SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
]


class Scanner:

    @staticmethod
    def run():

        collector = CandleCollector()

        print("\n========== MARKET SCANNER ==========\n")

        for symbol in SYMBOLS:

            try:

                # Отримуємо свічки
                df = collector.get_candles(symbol=symbol)

                # Додаємо всі індикатори (EMA, RSI, MACD, ATR)
                df = SignalIndicators.calculate(df)

                # Генеруємо сигнал
                result = SignalGenerator.generate(df)

                # Поточна ціна та ATR
                price = df.iloc[-1]["close"]
                atr = df.iloc[-1]["atr"]

                # Розрахунок ризику
                risk = RiskManager.calculate(
                    price,
                    atr,
                    result["signal"]
                )

                print(f"\n{symbol}")
                print("-" * 40)
                print(f"Signal : {result['signal']}")
                print(f"Score  : {result['score']}")
                print(f"Trend  : {result['trend']}")

                if risk:

                    print(f"Entry  : {risk['entry']}")
                    print(f"Stop   : {risk['stop']}")
                    print(f"TP1    : {risk['tp1']}")
                    print(f"TP2    : {risk['tp2']}")
                    print(f"TP3    : {risk['tp3']}")
                    print(f"RR     : 1:{risk['rr']}")

            except Exception as e:

                print(f"{symbol} -> ERROR: {e}")

        print("\n=====================================\n")


if __name__ == "__main__":
    Scanner.run()