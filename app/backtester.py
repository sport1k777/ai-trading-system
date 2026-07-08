from app.collectors.candles import CandleCollector
from app.indicators.signals import SignalIndicators
from app.analysis.signal_generator import SignalGenerator


class Backtester:

    @staticmethod
    def run():

        print("\n========== BACKTEST ==========\n")

        collector = CandleCollector()

        df = collector.get_candles(limit=1000)

        df = SignalIndicators.calculate(df)

        trades = []
        wins = 0
        losses = 0

        for i in range(250, len(df) - 10):

            history = df.iloc[: i + 1].copy()

            signal = SignalGenerator.generate(history)

            if signal["signal"] == "WAIT":
                continue

            entry = history.iloc[-1]["close"]

            future = df.iloc[i + 1:i + 6]

            result = "LOSS"

            if signal["signal"] == "BUY":

                if future["high"].max() > entry:
                    result = "WIN"

            elif signal["signal"] == "SELL":

                if future["low"].min() < entry:
                    result = "WIN"

            trades.append(result)

            if result == "WIN":
                wins += 1
            else:
                losses += 1

        total = wins + losses

        if total == 0:

            print("No trades found.")
            return

        winrate = round((wins / total) * 100, 2)

        print(f"Trades   : {total}")
        print(f"Wins     : {wins}")
        print(f"Losses   : {losses}")
        print(f"Win Rate : {winrate}%")

        print("\n==============================\n")


if __name__ == "__main__":

    Backtester.run()