import logging

from app.config import DEFAULT_CANDLE_LIMIT, DEFAULT_INTERVAL, DEFAULT_SYMBOL
from app.utils.bybit_client import BybitClient

logger = logging.getLogger(__name__)


class CandleCollector:
    """Fetches OHLCV candles via the shared Bybit client."""

    def __init__(self, client=None):
        self.client = client or BybitClient()

    def get_candles(
        self,
        symbol: str = DEFAULT_SYMBOL,
        interval: str = DEFAULT_INTERVAL,
        limit: int = DEFAULT_CANDLE_LIMIT,
    ):
        logger.debug("Fetching %s candles for %s (interval=%s)", limit, symbol, interval)
        return self.client.get_klines(symbol=symbol, interval=interval, limit=limit)


if __name__ == "__main__":
    from app.utils.logging_config import setup_logging

    setup_logging(__name__)
    collector = CandleCollector()
    df = collector.get_candles()
    print(df.tail())
