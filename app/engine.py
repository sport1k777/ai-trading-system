from app.pipeline import TradingPipeline
from app.utils.logging_config import setup_logging


def main():
    setup_logging("app.engine")
    pipeline = TradingPipeline()

    print("\n==============================")
    print("      AI TRADING SYSTEM")
    print("==============================")

    try:
        result = pipeline.analyze()
    except Exception as exc:
        print(f"\nError: {exc}")
        return

    signal = result.signal

    print("\n========== RESULT ==========\n")
    print(f"Trend       : {result.trend}")
    print(f"Structure   : {result.structure}")
    print(f"BOS         : {result.bos}")
    print(f"CHOCH       : {result.choch}")
    print(f"Liquidity   : {result.liquidity}")
    print(f"Order Block : {result.order_block}")
    print(f"FVG         : {result.fvg}")
    print()
    print(f"Signal      : {signal['signal']}")
    print(f"Setup       : {signal.get('setup_type', 'n/a')}")
    print(f"Score       : {signal['score']}")
    print("\nReasons:")
    for reason in signal["reasons"]:
        print(f"- {reason}")

    if result.swing_highs:
        print("\nLast Swing High:")
        print(result.swing_highs[-1])
    else:
        print("\nLast Swing High: none detected")

    if result.swing_lows:
        print("\nLast Swing Low:")
        print(result.swing_lows[-1])
    else:
        print("\nLast Swing Low: none detected")

    if result.risk:
        risk = result.risk
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
