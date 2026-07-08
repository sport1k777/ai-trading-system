import logging

from app.config import SCANNER_SYMBOLS
from app.pipeline import TradingPipeline
from app.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


class Scanner:

    @staticmethod
    def run():
        setup_logging("app.scanner")
        pipeline = TradingPipeline()

        print("\n========== MARKET SCANNER ==========\n")

        for symbol in SCANNER_SYMBOLS:
            try:
                result = pipeline.analyze(symbol=symbol)
                signal = result.signal

                print(f"\n{symbol}")
                print("-" * 40)
                print(f"Signal : {signal['signal']}")
                print(f"Score  : {signal['score']}")
                print(f"Trend  : {signal['trend']}")

                if result.risk:
                    risk = result.risk
                    print(f"Entry  : {risk['entry']}")
                    print(f"Stop   : {risk['stop']}")
                    print(f"TP1    : {risk['tp1']}")
                    print(f"TP2    : {risk['tp2']}")
                    print(f"TP3    : {risk['tp3']}")
                    print(f"RR     : 1:{risk['rr']}")

            except Exception as exc:
                logger.exception("Scanner failed for %s", symbol)
                print(f"{symbol} -> ERROR: {exc}")

        print("\n=====================================\n")


if __name__ == "__main__":
    Scanner.run()
